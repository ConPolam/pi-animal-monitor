#!/usr/bin/env python3
# display_gui.py - GUI显示界面

import sys
import time
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QTabWidget, QGroupBox, QGridLayout, QScrollArea,
                             QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
                             QSlider, QProgressBar, QMessageBox, QFileDialog,
                             QSplitter, QFrame, QAction, QMenu, QMenuBar,
                             QStatusBar, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot, QSize
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor, QPalette, QIcon
import pyqtgraph as pg
from datetime import datetime, timedelta
from collections import deque
import json
import os
from typing import Optional
from config import config
from utils import ImageProcessor, FPSMonitor, AlertSystem, logger
from network_client import network_manager
from animal_detector import animal_detector


class VideoDisplayWidget(QWidget):
    """视频显示组件"""

    frame_updated = pyqtSignal(np.ndarray, list)  # 图像，检测结果

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(640, 480)

        # 设置样式
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                border: 2px solid #3c3c3c;
                border-radius: 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        self.setLayout(layout)

        self.current_image = None
        self.current_detections = []

    @pyqtSlot(np.ndarray, list)
    def update_frame(self, image, detections):
        """更新显示帧"""
        self.current_image = image
        self.current_detections = detections

        # 绘制检测框
        if detections:
            image_with_detections = ImageProcessor.draw_detections(image.copy(), detections)
        else:
            image_with_detections = image.copy()

        # 转换为QPixmap
        height, width, channel = image_with_detections.shape
        bytes_per_line = 3 * width
        q_img = QImage(image_with_detections.data, width, height,
                       bytes_per_line, QImage.Format_RGB888)

        pixmap = QPixmap.fromImage(q_img)

        # 缩放以适应标签大小
        scaled_pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.frame_updated.emit(image, detections)

    def save_current_frame(self):
        """保存当前帧"""
        if self.current_image is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshots/frame_{timestamp}.jpg"

            # 确保目录存在
            os.makedirs("screenshots", exist_ok=True)

            # 绘制检测框并保存
            if self.current_detections:
                image_to_save = ImageProcessor.draw_detections(
                    self.current_image.copy(),
                    self.current_detections
                )
            else:
                image_to_save = self.current_image

            ImageProcessor.save_image(image_to_save, filename)
            return filename

        return None

        # 添加属性获取方法

    def get_current_image(self) -> Optional[np.ndarray]:
        """获取当前显示的图像"""
        return self.current_image

    def get_current_detections(self) -> list:
        """获取当前的检测结果"""
        return self.current_detections

    def has_valid_frame(self) -> bool:
        """检查是否有有效的帧"""
        return self.current_image is not None


class StatisticsWidget(QWidget):
    """统计信息显示组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

        # 数据存储
        self.fps_data = deque(maxlen=100)
        self.detection_data = deque(maxlen=100)
        self.animal_counts = {}

        # 更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_stats)
        self.update_timer.start(1000)  # 1秒更新一次

    def init_ui(self):
        """初始化UI"""
        layout = QGridLayout()

        # FPS图表
        self.fps_plot = pg.PlotWidget(title="FPS实时监控")
        self.fps_plot.setLabel('left', 'FPS')
        self.fps_plot.setLabel('bottom', '时间 (秒)')
        self.fps_plot.showGrid(x=True, y=True)
        self.fps_curve = self.fps_plot.plot(pen='g')
        layout.addWidget(self.fps_plot, 0, 0, 1, 2)

        # 检测数量图表
        self.detection_plot = pg.PlotWidget(title="检测数量统计")
        self.detection_plot.setLabel('left', '检测数量')
        self.detection_plot.setLabel('bottom', '时间 (秒)')
        self.detection_plot.showGrid(x=True, y=True)
        self.detection_curve = self.detection_plot.plot(pen='r')
        layout.addWidget(self.detection_plot, 0, 2, 1, 2)

        # 实时统计信息
        stats_group = QGroupBox("实时统计")
        stats_layout = QGridLayout()

        self.fps_label = QLabel("FPS: 0.0")
        self.avg_fps_label = QLabel("平均FPS: 0.0")
        self.total_frames_label = QLabel("总帧数: 0")
        self.total_detections_label = QLabel("总检测数: 0")

        stats_layout.addWidget(self.fps_label, 0, 0)
        stats_layout.addWidget(self.avg_fps_label, 0, 1)
        stats_layout.addWidget(self.total_frames_label, 1, 0)
        stats_layout.addWidget(self.total_detections_label, 1, 1)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group, 1, 0, 1, 4)

        # 动物检测统计表
        self.animal_table = QTableWidget()
        self.animal_table.setColumnCount(3)
        self.animal_table.setHorizontalHeaderLabels(["动物", "检测次数", "最后一次检测"])
        self.animal_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.animal_table, 2, 0, 1, 4)

        self.setLayout(layout)

    def update_stats(self, fps: float = None, detection_count: int = None):
        """更新统计信息"""
        if fps is not None:
            self.fps_data.append(fps)
            self.fps_label.setText(f"FPS: {fps:.1f}")

            if self.fps_data:
                avg_fps = np.mean(list(self.fps_data))
                self.avg_fps_label.setText(f"平均FPS: {avg_fps:.1f}")

            # 更新图表
            self.fps_curve.setData(list(self.fps_data))

        if detection_count is not None:
            self.detection_data.append(detection_count)
            self.total_detections_label.setText(f"总检测数: {sum(self.detection_data)}")

            # 更新图表
            self.detection_curve.setData(list(self.detection_data))

    def update_animal_stats(self, detections: list):
        """更新动物检测统计"""
        for detection in detections:
            animal_name = detection.animal_name
            if animal_name not in self.animal_counts:
                self.animal_counts[animal_name] = {
                    'count': 0,
                    'last_detection': None
                }

            self.animal_counts[animal_name]['count'] += 1
            self.animal_counts[animal_name]['last_detection'] = \
                detection.frame_timestamp.strftime("%H:%M:%S")

        # 更新表格
        self.animal_table.setRowCount(len(self.animal_counts))

        for row, (animal, stats) in enumerate(self.animal_counts.items()):
            self.animal_table.setItem(row, 0, QTableWidgetItem(animal))
            self.animal_table.setItem(row, 1, QTableWidgetItem(str(stats['count'])))
            self.animal_table.setItem(row, 2,
                                      QTableWidgetItem(stats['last_detection'] or "无"))

    def update_frame_count(self, count: int):
        """更新帧数统计"""
        self.total_frames_label.setText(f"总帧数: {count}")


class ControlPanelWidget(QWidget):
    """控制面板组件"""
    layout = QVBoxLayout()
    command_sent = pyqtSignal(str)  # 命令发送信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()

        # 连接控制组
        connection_group = QGroupBox("连接控制")
        connection_layout = QHBoxLayout()

        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.connect_camera)
        connection_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.clicked.connect(self.disconnect_camera)
        self.disconnect_btn.setEnabled(False)
        connection_layout.addWidget(self.disconnect_btn)

        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)

        # 视频控制组
        video_group = QGroupBox("视频控制")
        video_layout = QGridLayout()

        # 修改保存帧按钮的文本和提示
        self.save_frame_btn = QPushButton("保存视频帧（带检测）")
        self.save_frame_btn.clicked.connect(self.save_current_frame)
        self.save_frame_btn.setToolTip("保存当前帧并进行动物检测")
        video_layout.addWidget(self.save_frame_btn, 1, 1)

        self.start_stream_btn = QPushButton("开始流")
        self.start_stream_btn.clicked.connect(self.start_stream)
        self.start_stream_btn.setEnabled(False)
        video_layout.addWidget(self.start_stream_btn, 0, 0)

        self.stop_stream_btn = QPushButton("停止流")
        self.stop_stream_btn.clicked.connect(self.stop_stream)
        self.stop_stream_btn.setEnabled(False)
        video_layout.addWidget(self.stop_stream_btn, 0, 1)

        #self.capture_btn = QPushButton("抓拍")
        #self.capture_btn.clicked.connect(self.capture_frame)
        #video_layout.addWidget(self.capture_btn, 1, 0)

        #self.save_frame_btn = QPushButton("保存当前帧")
        #self.save_frame_btn.clicked.connect(self.save_current_frame)
        #video_layout.addWidget(self.save_frame_btn, 1, 1)

        #video_group.setLayout(video_layout)
        #layout.addWidget(video_group)

        # 修改保存帧按钮，占用原来两个按钮的位置（居中显示）
        self.save_frame_btn = QPushButton("保存并检测当前帧")
        self.save_frame_btn.clicked.connect(self.save_current_frame)
        #self.save_frame_btn.setMinimumHeight(40)  # 增加高度，更显眼

        # 将按钮放在第1行，第0列，跨越4列（整个视频控制组的宽度）
        video_layout.addWidget(self.save_frame_btn, 1, 0, 1, 2)

        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # 检测控制组
        detection_group = QGroupBox("检测控制")
        detection_layout = QGridLayout()

        detection_layout.addWidget(QLabel("置信度阈值:"), 0, 0)
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(10, 95)  # 0.1-0.95
        self.confidence_slider.setValue(int(config.MODEL_CONFIDENCE * 100))
        self.confidence_slider.valueChanged.connect(self.confidence_changed)
        detection_layout.addWidget(self.confidence_slider, 0, 1)

        self.confidence_label = QLabel(f"{config.MODEL_CONFIDENCE:.2f}")
        detection_layout.addWidget(self.confidence_label, 0, 2)

        detection_layout.addWidget(QLabel("报警动物:"), 1, 0)
        self.alert_animal_combo = QComboBox()
        self.alert_animal_combo.addItems(config.IMPORTANT_ANIMALS)
        detection_layout.addWidget(self.alert_animal_combo, 1, 1)

        self.alert_enable_check = QCheckBox("启用报警")
        self.alert_enable_check.setChecked(config.ALERT_ENABLED)
        detection_layout.addWidget(self.alert_enable_check, 2, 0, 1, 2)

        detection_group.setLayout(detection_layout)
        layout.addWidget(detection_group)

        # 日志显示
        log_group = QGroupBox("系统日志")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        self.setLayout(layout)

    def connect_camera(self):
        """连接摄像头"""
        self.command_sent.emit("CONNECT")

    def disconnect_camera(self):
        """断开摄像头"""
        self.command_sent.emit("DISCONNECT")

    def start_stream(self):
        """开始视频流"""
        self.command_sent.emit("START")

    def stop_stream(self):
        """停止视频流"""
        self.command_sent.emit("STOP")

    def capture_frame(self):
        """抓拍单帧"""
        self.command_sent.emit("TAKE")

    def save_current_frame(self):
        """保存当前帧"""
        self.command_sent.emit("SAVE_FRAME")

    def confidence_changed(self, value):
        """置信度阈值改变"""
        confidence = value / 100.0
        self.confidence_label.setText(f"{confidence:.2f}")
        self.command_sent.emit(f"SET_CONFIDENCE:{confidence}")

    def add_log(self, message: str):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

        # 限制日志行数
        lines = self.log_text.toPlainText().split('\n')
        if len(lines) > 100:
            self.log_text.setPlainText('\n'.join(lines[-100:]))

        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def update_connection_status(self, connected: bool, streaming: bool = False):
        """更新连接状态"""
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        self.start_stream_btn.setEnabled(connected and not streaming)
        self.stop_stream_btn.setEnabled(connected and streaming)
        #self.capture_btn.setEnabled(connected)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        # 初始化组件
        self.video_display = VideoDisplayWidget()
        self.statistics_widget = StatisticsWidget()
        self.control_panel = ControlPanelWidget()

        # 初始化系统组件
        self.fps_monitor = FPSMonitor()
        self.alert_system = AlertSystem(config.IMPORTANT_ANIMALS, config.ALERT_COOLDOWN)
        self.image_processor = ImageProcessor()

        # 状态变量
        self.is_connected = False
        self.is_streaming = False
        self.frame_counter = 0
        self.last_processed_time = time.time()

        # 初始化UI
        self.init_ui()

        # 设置定时器
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.process_frames)
        self.process_timer.start(33)  # ~30 FPS

        # 连接信号
        self.setup_connections()

        # 初始状态
        self.update_ui_status()

        # 在MainWindow类的__init__方法中添加
        self.is_capturing = False  # 抓拍状态标志
        self.capture_retry_count = 0  # 抓拍重试计数

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle("动物识别系统 - B端 (PC主机)")
        self.setGeometry(100, 100, 1600, 900)

        # 设置应用图标
        # self.setWindowIcon(QIcon('icon.png'))

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout()

        # 左侧面板（视频显示和统计）
        left_panel = QVBoxLayout()
        left_panel.addWidget(self.video_display, 2)
        left_panel.addWidget(self.statistics_widget, 1)

        # 右侧面板（控制面板）
        right_panel = QVBoxLayout()
        right_panel.addWidget(self.control_panel)

        # 添加到主布局
        main_layout.addLayout(left_panel, 3)
        main_layout.addLayout(right_panel, 1)

        central_widget.setLayout(main_layout)

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 状态栏标签
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

        self.fps_status_label = QLabel("FPS: 0.0")
        self.status_bar.addPermanentWidget(self.fps_status_label)

        self.detection_status_label = QLabel("检测数: 0")
        self.status_bar.addPermanentWidget(self.detection_status_label)

        # 创建菜单栏
        self.create_menu_bar()

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu('文件')

        save_action = QAction('保存当前帧', self)
        save_action.triggered.connect(self.save_current_frame)
        file_menu.addAction(save_action)

        save_log_action = QAction('保存日志', self)
        save_log_action.triggered.connect(self.save_log)
        file_menu.addAction(save_log_action)

        file_menu.addSeparator()

        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 设置菜单
        settings_menu = menubar.addMenu('设置')

        model_settings_action = QAction('模型设置', self)
        model_settings_action.triggered.connect(self.show_model_settings)
        settings_menu.addAction(model_settings_action)

        network_settings_action = QAction('网络设置', self)
        network_settings_action.triggered.connect(self.show_network_settings)
        settings_menu.addAction(network_settings_action)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助')

        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_connections(self):
        """设置信号连接"""
        # 控制面板信号
        self.control_panel.command_sent.connect(self.handle_command)

        # 视频显示信号
        self.video_display.frame_updated.connect(self.on_frame_updated)

    @pyqtSlot(str)
    def handle_command(self, command: str):
        """处理控制命令"""
        try:
            if command == "CONNECT":
                self.connect_to_camera()
            elif command == "DISCONNECT":
                self.disconnect_from_camera()
            elif command == "START":
                self.start_video_stream()
            elif command == "STOP":
                self.stop_video_stream()
            elif command == "TAKE":
                self.capture_single_frame()
            elif command == "SAVE_FRAME":
                self.save_current_frame()
            elif command.startswith("SET_CONFIDENCE:"):
                confidence = float(command.split(":")[1])
                self.set_confidence_threshold(confidence)

            self.control_panel.add_log(f"执行命令: {command}")

        except Exception as e:
            logger.error(f"处理命令失败: {e}")
            self.control_panel.add_log(f"错误: {str(e)}")

    def connect_to_camera(self):
        """连接到摄像头"""
        if not self.is_connected:
            if network_manager.start():
                self.is_connected = True
                self.control_panel.add_log("已连接到树莓派摄像头")
            else:
                self.control_panel.add_log("连接失败")
        else:
            self.control_panel.add_log("已连接")

        self.update_ui_status()

    def disconnect_from_camera(self):
        """断开摄像头连接"""
        if self.is_connected:
            network_manager.stop()
            self.is_connected = False
            self.is_streaming = False
            self.control_panel.add_log("已断开连接")

        self.update_ui_status()

    def start_video_stream(self):
        """开始视频流"""
        if self.is_connected and not self.is_streaming:
            self.is_streaming = True
            self.control_panel.add_log("开始接收视频流")

        self.update_ui_status()

    def stop_video_stream(self):
        """停止视频流"""
        if self.is_streaming:
            self.is_streaming = False
            self.control_panel.add_log("停止视频流")

        self.update_ui_status()






    #this



    def capture_single_frame(self):
        """捕获单帧 - 修复GUI卡死问题"""
        if not self.is_connected:
            self.control_panel.add_log("错误: 未连接到摄像头")
            return

        # 防止重复点击
        if self.control_panel.capture_btn.isEnabled() == False:
            self.control_panel.add_log("正在抓拍中，请稍候...")
            return

        self.control_panel.add_log("开始抓拍...")

        # 禁用抓拍按钮
        self.control_panel.capture_btn.setEnabled(False)

        # 使用QThread而不是普通thread，避免GUI卡死
        from PyQt5.QtCore import QThread

        class CaptureThread(QThread):
            finished = pyqtSignal(bool, bytes, str)  # 成功, 数据, 消息

            def __init__(self, client, was_streaming, parent=None):
                super().__init__(parent)
                self.client = client
                self.was_streaming = was_streaming

            def run(self):
                try:
                    # 如果正在流，先暂停
                    if self.was_streaming:
                        self.client.send_command("STOP")
                        import time
                        time.sleep(0.5)

                    # 抓拍
                    frame_data = self.client.capture_single_frame()

                    if frame_data:
                        self.finished.emit(True, frame_data, "抓拍成功")
                    else:
                        self.finished.emit(False, b'', "抓拍失败")

                except Exception as e:
                    import traceback
                    error_msg = f"抓拍出错: {str(e)}\n{traceback.format_exc()}"
                    self.finished.emit(False, b'', error_msg)

        # 创建并启动线程
        client = network_manager.get_client()
        was_streaming = self.is_streaming

        self.capture_thread = CaptureThread(client, was_streaming)
        self.capture_thread.finished.connect(self._on_capture_finished)
        self.capture_thread.start()

    def _on_capture_finished(self, success: bool, frame_data: bytes, message: str):
        """抓拍完成回调"""
        self.control_panel.add_log(message)

        if success and frame_data:
            # 处理抓拍到的图片
            self.process_captured_frame(frame_data)

        # 恢复视频流（如果需要）
        import threading
        def restore_stream():
            import time
            time.sleep(0.5)

            client = network_manager.get_client()
            if client:
                client.send_command("START")
                QTimer.singleShot(0, lambda: setattr(self, 'is_streaming', True))
                self.control_panel.add_log("视频流已恢复")

        # 如果需要恢复视频流，在新线程中执行
        if hasattr(self, 'capture_thread') and self.capture_thread.was_streaming:
            threading.Thread(target=restore_stream, daemon=True).start()

        # 恢复按钮状态
        self.control_panel.capture_btn.setEnabled(True)

        # 清理线程引用
        if hasattr(self, 'capture_thread'):
            self.capture_thread.quit()
            self.capture_thread.wait()
            del self.capture_thread

        # 更新UI状态
        self.update_ui_status()

    def process_captured_frame(self, frame_data: bytes):
        """处理捕获的帧"""
        try:
            # 解码图像
            image = self.image_processor.decode_jpeg(frame_data)
            if image is not None:
                # 检测动物
                detections = animal_detector.detect_animals(image, self.frame_counter)

                # 更新显示
                self.video_display.update_frame(image, detections)

                # 保存抓拍图片
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshots/capture_{timestamp}.jpg"
                import os
                os.makedirs("screenshots", exist_ok=True)
                from utils import ImageProcessor
                ImageProcessor.save_image(image, filename)

                # 显示抓拍弹窗（在主线程中）
                self.show_capture_success(detections, filename)

            else:
                self.control_panel.add_log("❌ 抓拍失败：图像解码失败")

        except Exception as e:
            logger.error(f"处理捕获帧失败: {e}")
            self.control_panel.add_log(f"❌ 处理抓拍失败: {str(e)}")

    def _restore_stream_safe(self):
        """安全恢复视频流"""
        self.control_panel.add_log("安全恢复视频流...")

        import threading

        def restore_thread():
            client = network_manager.get_client()
            if not client:
                self.control_panel.add_log("错误: 客户端未连接")
                return

            try:
                # 先确保连接正常
                import time
                time.sleep(0.5)

                # 发送START命令
                success = client.send_command("START")
                if success:
                    time.sleep(0.5)  # 等待A端处理

                    # 更新状态
                    QTimer.singleShot(0, lambda: setattr(self, 'is_streaming', True))
                    self.control_panel.add_log("视频流已恢复")
                else:
                    self.control_panel.add_log("恢复视频流失败，请手动重试")
            except Exception as e:
                self.control_panel.add_log(f"恢复视频流出错: {str(e)}")

        threading.Thread(target=restore_thread, daemon=True).start()






    def _restore_stream_with_retry(self):
        """恢复视频流，带重试机制"""
        self.control_panel.add_log("尝试恢复视频流...")

        import threading
        import time

        def restore_thread():
            client = network_manager.get_client()
            if not client:
                self.control_panel.add_log("错误: 客户端未连接")
                return

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.control_panel.add_log(f"尝试恢复视频流 (尝试 {attempt + 1}/{max_retries})...")

                    # 发送START命令
                    success = client.send_command("START")

                    if success:
                        # 等待一段时间确认流已恢复
                        time.sleep(0.5)

                        # 检查连接是否正常
                        if client.connected and client.receiving:
                            # 在主线程中更新状态
                            QTimer.singleShot(0, lambda: setattr(self, 'is_streaming', True))
                            self.control_panel.add_log("视频流已恢复")
                            return True
                        else:
                            self.control_panel.add_log("连接状态异常，重试...")
                    else:
                        self.control_panel.add_log("发送START命令失败")

                    # 等待后重试
                    time.sleep(1)

                except Exception as e:
                    self.control_panel.add_log(f"恢复视频流出错: {str(e)}")

            self.control_panel.add_log("恢复视频流失败")
            return False

        threading.Thread(target=restore_thread, daemon=True).start()

    def process_captured_frame(self, frame_data: bytes):
        """处理捕获的帧"""
        try:
            # 解码图像
            image = self.image_processor.decode_jpeg(frame_data)
            if image is not None:
                # 检测动物
                detections = animal_detector.detect_animals(image, self.frame_counter)

                # 更新显示
                self.video_display.update_frame(image, detections)

                # 保存抓拍图片
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshots/capture_{timestamp}.jpg"
                os.makedirs("screenshots", exist_ok=True)
                ImageProcessor.save_image(image, filename)

                # 记录日志
                if detections:
                    self.control_panel.add_log(f"✅ 抓拍成功！检测到 {len(detections)} 个动物")
                    for det in detections:
                        self.control_panel.add_log(f"   - {det.animal_name}: {det.confidence:.2%}")
                else:
                    self.control_panel.add_log(f"✅ 抓拍成功！没有检测到动物")

                # 显示抓拍弹窗
                self.show_capture_success(detections, filename)

            else:
                self.control_panel.add_log("❌ 抓拍失败：图像解码失败")

        except Exception as e:
            logger.error(f"处理捕获帧失败: {e}")
            self.control_panel.add_log(f"❌ 处理抓拍失败: {str(e)}")

    def show_capture_success(self, detections: list, filename: str):
        """显示抓拍成功消息"""
        if detections:
            animal_list = ', '.join([f"{d.animal_name}({d.confidence:.0%})" for d in detections])
            msg = f"抓拍成功！\n\n检测到: {animal_list}\n\n图片已保存到:\n{filename}"
        else:
            msg = f"抓拍成功！\n\n没有检测到动物\n\n图片已保存到:\n{filename}"

        # 创建自定义对话框
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

        dialog = QDialog(self)
        dialog.setWindowTitle("抓拍成功")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # 消息标签
        label = QLabel(msg)
        label.setWordWrap(True)
        layout.addWidget(label)

        # 按钮
        btn = QPushButton("确定")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)

        dialog.setLayout(layout)
        dialog.exec_()

    def process_frames(self):
        """处理视频帧（定时器调用）"""
        if not self.is_connected or not self.is_streaming:
            return

        # 限制处理频率
        current_time = time.time()
        if current_time - self.last_processed_time < 0.033:  # ~30 FPS
            return

        try:
            # 获取下一帧
            frame_data = network_manager.get_client().get_next_frame(timeout=0.01)
            if not frame_data:
                return

            self.last_processed_time = current_time
            self.frame_counter += 1

            # 解码图像
            image = self.image_processor.decode_jpeg(frame_data)
            if image is None:
                logger.warning(f"第 {self.frame_counter} 帧解码失败")
                return

            # 直接更新显示，不等待检测结果
            self.video_display.update_frame(image, [])

            # 异步检测动物（不阻塞UI）
            try:
                if hasattr(animal_detector, 'detect_async'):
                    future = animal_detector.detect_async(image, self.frame_counter)
                    future.add_done_callback(lambda f: self.on_detection_complete(f, image))
            except Exception as e:
                logger.error(f"启动异步检测失败: {e}")

            # 更新FPS
            fps = self.fps_monitor.update()
            self.fps_status_label.setText(f"FPS: {fps:.1f}")

            # 更新统计
            self.statistics_widget.update_frame_count(self.frame_counter)
            self.statistics_widget.update_stats(fps)

        except Exception as e:
            logger.error(f"处理帧失败: {e}")

    def on_detection_complete(self, future, image: np.ndarray):
        """检测完成回调"""
        try:
            detections = future.result()

            # 在UI线程中更新显示
            QTimer.singleShot(0, lambda: self.update_display(image, detections))

        except Exception as e:
            logger.error(f"获取检测结果失败: {e}")

    def update_display(self, image: np.ndarray, detections: list):
        """更新显示"""
        # 更新视频显示
        self.video_display.update_frame(image, detections)

        # 更新统计信息
        detection_count = len(detections)
        self.detection_status_label.setText(f"检测数: {detection_count}")
        self.statistics_widget.update_stats(detection_count=detection_count)

        if detections:
            self.statistics_widget.update_animal_stats(detections)

            # 检查重要检测
            important_detections = animal_detector.get_important_detections(detections)
            for detection in important_detections:
                if (config.ALERT_ENABLED and
                        self.control_panel.alert_enable_check.isChecked() and
                        self.alert_system.should_alert(detection.animal_name)):
                    alert_msg = self.alert_system.get_alert_message(
                        detection.animal_name, detection.confidence
                    )
                    self.control_panel.add_log(f"⚠️ {alert_msg}")

                    # 显示报警弹窗
                    self.show_alert_message(detection.animal_name)

    @pyqtSlot(np.ndarray, list)
    def on_frame_updated(self, image, detections):
        """帧更新回调"""
        # 可以在这里添加额外的处理
        pass

    def save_current_frame(self):
        """保存当前帧（带动物检测）"""
        if not hasattr(self.video_display, 'current_image') or self.video_display.current_image is None:
            self.control_panel.add_log("没有可保存的图像")
            QMessageBox.warning(self, "保存失败", "当前没有图像可保存")
            return

        # 获取当前图像和检测结果
        current_image = self.video_display.current_image
        detections = self.video_display.current_detections

        # 如果没有检测结果，则进行动物检测
        if not detections:
            self.control_panel.add_log("正在检测动物...")

            # 使用独立的线程进行检测，避免GUI卡顿
            from PyQt5.QtCore import QThread

            class DetectionThread(QThread):
                finished = pyqtSignal(list, str)  # 检测结果，消息

                def __init__(self, image, frame_counter):
                    super().__init__()
                    self.image = image
                    self.frame_counter = frame_counter

                def run(self):
                    try:
                        # 进行动物检测
                        detections = animal_detector.detect_animals(self.image, self.frame_counter)
                        if detections:
                            self.finished.emit(detections, f"检测到 {len(detections)} 个动物")
                        else:
                            self.finished.emit([], "未检测到动物")
                    except Exception as e:
                        import traceback
                        error_msg = f"检测失败: {str(e)}"
                        self.finished.emit([], error_msg)

            # 创建并启动检测线程
            self.detection_thread = DetectionThread(current_image, self.frame_counter)
            self.detection_thread.finished.connect(self._on_detection_finished_for_save)
            self.detection_thread.start()
        else:
            # 如果已经有检测结果，直接保存
            self._save_image_with_detections(current_image, detections)

    def _on_detection_finished_for_save(self, detections: list, message: str):
        """检测完成回调（用于保存）"""
        self.control_panel.add_log(message)

        if detections:
            # 显示检测到的动物信息
            for detection in detections:
                self.control_panel.add_log(f"  - {detection.animal_name}: 置信度 {detection.confidence:.2%}")

        # 获取当前图像（再次确认是最新的）
        current_image = self.video_display.current_image
        if current_image is not None:
            self._save_image_with_detections(current_image, detections)

        # 清理线程引用
        if hasattr(self, 'detection_thread'):
            self.detection_thread.quit()
            self.detection_thread.wait()
            del self.detection_thread

    def _save_image_with_detections(self, image: np.ndarray, detections: list):
        """保存带检测结果的图像"""
        try:
            # 绘制检测框
            if detections:
                image_with_detections = ImageProcessor.draw_detections(image.copy(), detections)
            else:
                image_with_detections = image.copy()

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 根据是否有检测结果命名文件
            if detections:
                animal_names = [d.animal_name for d in detections]
                unique_animals = list(set(animal_names))
                animal_str = "_".join(unique_animals)
                filename = f"screenshots/detection_{animal_str}_{timestamp}.jpg"
            else:
                filename = f"screenshots/frame_{timestamp}.jpg"

            # 确保目录存在
            os.makedirs("screenshots", exist_ok=True)

            # 保存图像
            ImageProcessor.save_image(image_with_detections, filename)

            # 记录到数据库
            try:
                from database import db_manager
                for detection in detections:
                    bbox = detection.bbox
                    db_manager.add_detection(
                        animal_name=detection.animal_name,
                        confidence=detection.confidence,
                        bbox=bbox,
                        frame_size=(image.shape[1], image.shape[0]),  # 宽, 高
                        frame_index=self.frame_counter,
                        image_path=filename
                    )
            except Exception as e:
                logger.error(f"保存检测记录失败: {e}")

            # 显示成功消息
            msg = f"已保存帧到: {filename}"
            if detections:
                msg += f"\n检测到 {len(detections)} 个动物"
                for detection in detections:
                    msg += f"\n- {detection.animal_name} ({detection.confidence:.1%})"

            self.control_panel.add_log(msg)
            QMessageBox.information(self, "保存成功", msg)

        except Exception as e:
            logger.error(f"保存图像失败: {e}")
            self.control_panel.add_log(f"保存失败: {str(e)}")
            QMessageBox.warning(self, "保存失败", f"保存图像失败: {str(e)}")

    def save_log(self):
        """保存日志"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存日志", "", "Text Files (*.txt);;All Files (*)"
        )

        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.control_panel.log_text.toPlainText())
                self.control_panel.add_log(f"日志已保存到: {filename}")
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"保存日志失败: {str(e)}")

    def set_confidence_threshold(self, confidence: float):
        """设置置信度阈值"""
        animal_detector.confidence_threshold = confidence
        config.MODEL_CONFIDENCE = confidence
        self.control_panel.add_log(f"置信度阈值设置为: {confidence:.2f}")

    def show_model_settings(self):
        """显示模型设置对话框"""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("模型设置")

        model_stats = animal_detector.get_system_statistics()
        message = f"""
        模型信息:
        模型路径: {animal_detector.model_path}
        使用设备: {animal_detector.device}
        置信度阈值: {animal_detector.confidence_threshold:.2f}
        IOU阈值: {animal_detector.iou_threshold:.2f}

        统计信息:
        处理帧数: {model_stats['frames_processed']}
        总检测数: {model_stats['total_detections']}
        平均检测时间: {model_stats.get('avg_detection_time', 0):.3f}秒
        检测率: {model_stats.get('detection_rate', 0):.2f}/帧
        """

        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec_()

    def show_network_settings(self):
        """显示网络设置对话框"""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("网络设置")

        client = network_manager.get_client()
        stats = client.get_statistics() if client else {}

        message = f"""
        网络配置:
        目标主机: {config.HOST}
        目标端口: {config.PORT}

        连接状态: {'已连接' if self.is_connected else '未连接'}
        流状态: {'运行中' if self.is_streaming else '停止'}

        统计信息:
        接收帧数: {stats.get('frames_received', 0)}
        接收字节: {stats.get('bytes_received', 0)} bytes
        队列大小: {stats.get('queue_size', 0)}
        """

        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec_()

    def show_alert_message(self, animal_name: str):
        """显示报警消息"""
        QMessageBox.warning(
            self,
            "动物检测报警",
            f"检测到 {animal_name}！\n请查看详情。"
        )

    def show_about(self):
        """显示关于对话框"""
        about_text = """
        <h2>动物识别系统 - B端</h2>
        <p>版本: 1.0.0</p>
        <p>功能:</p>
        <ul>
            <li>连接树莓派摄像头</li>
            <li>实时动物检测（使用YOLOv8）</li>
            <li>检测结果显示与统计</li>
            <li>报警系统</li>
            <li>数据记录与导出</li>
        </ul>
        <p>技术支持: DeepSeek AI Assistant</p>
        """

        QMessageBox.about(self, "关于动物识别系统", about_text)

    def update_ui_status(self):
        """更新UI状态"""
        self.control_panel.update_connection_status(
            self.is_connected, self.is_streaming
        )

        # 更新状态栏
        status_text = "已连接" if self.is_connected else "未连接"
        if self.is_streaming:
            status_text += " (流媒体中)"
        self.status_label.setText(status_text)

    def closeEvent(self, event):
        """关闭事件处理"""
        reply = QMessageBox.question(
            self, '确认退出',
            '确定要退出动物识别系统吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 清理资源
            self.disconnect_from_camera()
            animal_detector.close()
            event.accept()
        else:
            event.ignore()


def main():
    """主函数"""
    app = QApplication(sys.argv)

    # 设置应用程序样式
    app.setStyle('Fusion')

    # 设置调色板（暗色主题）
    if config.UI_THEME == "dark":
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(palette)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 记录启动信息
    logger.info("动物识别系统B端启动")
    logger.info(f"目标设备: {config.HOST}:{config.PORT}")
    logger.info(f"使用模型: {config.MODEL_PATH}")

    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()