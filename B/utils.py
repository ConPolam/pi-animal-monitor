#!/usr/bin/env python3
# utils.py - 工具函数
import concurrent
import os

import cv2
import numpy as np
import struct
import time
import json
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Any, Dict
from dataclasses import dataclass
import pickle

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/animal_recognition.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """检测结果数据结构"""
    animal_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    frame_timestamp: datetime
    frame_index: int

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "animal": self.animal_name,
            "confidence": round(self.confidence, 3),
            "bbox": self.bbox,
            "timestamp": self.frame_timestamp.isoformat(),
            "frame_index": self.frame_index
        }


class ImageProcessor:
    """图像处理器"""

    @staticmethod
    def save_image_with_detections(image: np.ndarray, detections: List[DetectionResult],
                                   filename: str = None) -> str:
        """保存带检测框的图像"""
        if detections:
            image_to_save = ImageProcessor.draw_detections(image.copy(), detections)
        else:
            image_to_save = image.copy()

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshots/frame_{timestamp}.jpg"

        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # 转换为BGR格式保存
        img_bgr = cv2.cvtColor(image_to_save, cv2.COLOR_RGB2BGR)
        cv2.imwrite(filename, img_bgr)
        logger.info(f"图像已保存: {filename}")
        return filename

    @staticmethod
    def create_detection_summary(detections: List[DetectionResult]) -> Dict[str, Any]:
        """创建检测结果摘要"""
        summary = {
            "total": len(detections),
            "animals": {},
            "timestamp": datetime.now().isoformat()
        }

        for detection in detections:
            animal = detection.animal_name
            if animal not in summary["animals"]:
                summary["animals"][animal] = {
                    "count": 0,
                    "max_confidence": 0,
                    "min_confidence": 1,
                    "average_confidence": 0
                }

            stats = summary["animals"][animal]
            stats["count"] += 1
            stats["max_confidence"] = max(stats["max_confidence"], detection.confidence)
            stats["min_confidence"] = min(stats["min_confidence"], detection.confidence)

        # 计算平均置信度
        for animal, stats in summary["animals"].items():
            if stats["count"] > 0:
                # 重新计算平均值
                total_confidence = sum(
                    d.confidence for d in detections
                    if d.animal_name == animal
                )
                stats["average_confidence"] = total_confidence / stats["count"]

        return summary


    @staticmethod
    def decode_jpeg(data: bytes) -> Optional[np.ndarray]:
        """解码JPEG数据为numpy数组"""
        try:
            # 将字节数据转换为numpy数组
            nparr = np.frombuffer(data, np.uint8)
            # 解码为图像
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                # 转换为RGB格式（OpenCV默认BGR）
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                return img_rgb
        except Exception as e:
            logger.error(f"JPEG解码失败: {e}")
        return None

    @staticmethod
    def draw_detections(image: np.ndarray, detections: List[DetectionResult]) -> np.ndarray:
        """在图像上绘制检测框和标签"""
        img_display = image.copy()

        for detection in detections:
            # 获取动物颜色
            color = (0, 255, 0)  # 默认绿色

            # 绘制边界框
            x1, y1, x2, y2 = detection.bbox
            cv2.rectangle(img_display, (x1, y1), (x2, y2), color, 2)

            # 绘制标签背景
            label = f"{detection.animal_name}: {detection.confidence:.2f}"
            (text_width, text_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
            )

            # 标签矩形
            cv2.rectangle(
                img_display,
                (x1, y1 - text_height - baseline - 5),
                (x1 + text_width, y1),
                color,
                -1  # 填充
            )

            # 标签文本
            cv2.putText(
                img_display,
                label,
                (x1, y1 - baseline - 3),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),  # 黑色文本
                2
            )

            # 在框的角落添加小标记
            marker_size = 5
            cv2.line(img_display, (x1, y1), (x1 + marker_size, y1), (255, 255, 255), 2)
            cv2.line(img_display, (x1, y1), (x1, y1 + marker_size), (255, 255, 255), 2)
            cv2.line(img_display, (x2, y1), (x2 - marker_size, y1), (255, 255, 255), 2)
            cv2.line(img_display, (x2, y1), (x2, y1 + marker_size), (255, 255, 255), 2)
            cv2.line(img_display, (x1, y2), (x1 + marker_size, y2), (255, 255, 255), 2)
            cv2.line(img_display, (x1, y2), (x1, y2 - marker_size), (255, 255, 255), 2)
            cv2.line(img_display, (x2, y2), (x2 - marker_size, y2), (255, 255, 255), 2)
            cv2.line(img_display, (x2, y2), (x2, y2 - marker_size), (255, 255, 255), 2)

        return img_display

    @staticmethod
    def save_image(image: np.ndarray, filename: str = None) -> str:
        """保存图像到文件"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshots/detection_{timestamp}.jpg"

        # 确保目录存在
        os.makedirs("screenshots", exist_ok=True)

        # 转换为BGR格式保存
        img_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        cv2.imwrite(filename, img_bgr)
        logger.info(f"图像已保存: {filename}")
        return filename

    @staticmethod
    def resize_image(image: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
        """调整图像大小"""
        return cv2.resize(image, target_size, interpolation=cv2.INTER_LINEAR)


class FPSMonitor:
    """FPS监控器"""

    def __init__(self):
        self.frame_count = 0
        self.start_time = time.time()
        self.fps_history = []
        self.max_history = 100

    def update(self) -> float:
        """更新并返回当前FPS"""
        self.frame_count += 1
        elapsed = time.time() - self.start_time

        if elapsed > 0:
            fps = self.frame_count / elapsed
        else:
            fps = 0

        # 每30帧重置一次
        if self.frame_count >= 30:
            self.frame_count = 0
            self.start_time = time.time()

        # 记录历史
        self.fps_history.append(fps)
        if len(self.fps_history) > self.max_history:
            self.fps_history.pop(0)

        return fps

    def get_average_fps(self) -> float:
        """获取平均FPS"""
        if not self.fps_history:
            return 0
        return np.mean(self.fps_history)

    def get_statistics(self) -> Dict[str, float]:
        """获取统计信息"""
        if not self.fps_history:
            return {"current": 0, "average": 0, "min": 0, "max": 0}

        return {
            "current": self.fps_history[-1] if self.fps_history else 0,
            "average": np.mean(self.fps_history),
            "min": np.min(self.fps_history),
            "max": np.max(self.fps_history)
        }


class AlertSystem:
    """报警系统"""

    def __init__(self, important_animals: List[str], cooldown: int = 30):
        self.important_animals = important_animals
        self.cooldown = cooldown
        self.last_alert_time = {}
        self.alert_count = 0
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def should_alert(self, animal_name: str) -> bool:
        """检查是否需要报警"""
        if animal_name not in self.important_animals:
            return False

        current_time = time.time()
        last_time = self.last_alert_time.get(animal_name, 0)

        if current_time - last_time >= self.cooldown:
            self.last_alert_time[animal_name] = current_time
            self.alert_count += 1
            return True

        return False

    def get_alert_message(self, animal_name: str, confidence: float) -> str:
        """获取报警消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] 检测到 {animal_name} (置信度: {confidence:.2%})"

    def get_statistics(self) -> Dict[str, Any]:
        """获取报警统计"""
        return {
            "total_alerts": self.alert_count,
            "last_alerts": self.last_alert_time
        }


def save_detection_log(detections: List[DetectionResult], log_file: str = "logs/detections.json"):
    """保存检测日志"""
    try:
        log_data = [det.to_dict() for det in detections]

        # 读取现有日志
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                log_data = existing_data + log_data

        # 保存日志
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"保存检测日志失败: {e}")