#!/usr/bin/env python3
# main.py - 主程序入口

import sys
import os
import argparse
import signal
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config
from utils import logger
from network_client import network_manager
from animal_detector import animal_detector
from database import db_manager


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='动物识别系统B端')

    parser.add_argument('--host', type=str, default=config.HOST,
                        help=f'树莓派IP地址 (默认: {config.HOST})')
    parser.add_argument('--port', type=int, default=config.PORT,
                        help=f'端口号 (默认: {config.PORT})')
    parser.add_argument('--model', type=str, default=config.MODEL_PATH,
                        help=f'模型路径 (默认: {config.MODEL_PATH})')
    parser.add_argument('--nogui', action='store_true',
                        help='不使用GUI界面，仅命令行模式')
    parser.add_argument('--log-level', type=str, default=config.LOG_LEVEL,
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别 (默认: INFO)')
    parser.add_argument('--export', type=str,
                        help='导出数据到指定文件 (CSV或JSON)')

    return parser.parse_args()


def setup_signal_handlers():
    """设置信号处理器"""

    def signal_handler(sig, frame):
        logger.info("收到关闭信号，正在清理资源...")
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def initialize_system():
    """初始化系统"""
    logger.info("=" * 60)
    logger.info("动物识别系统B端 - 初始化")
    logger.info("=" * 60)

    # 输出系统信息
    logger.info(f"系统时间: {datetime.now()}")
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"工作目录: {os.getcwd()}")

    # 检查模型文件
    if not os.path.exists(config.MODEL_PATH):
        logger.warning(f"模型文件不存在: {config.MODEL_PATH}")
        logger.info("正在尝试下载模型...")
        download_model()

    # 保存模型信息
    animal_detector.save_model_info()

    logger.info("系统初始化完成")


def download_model():
    """下载预训练模型"""
    try:
        from ultralytics import YOLO
        logger.info("正在下载YOLOv8n模型...")
        model = YOLO('yolov8n.pt')  # 会自动下载
        logger.info("模型下载完成")

        # 移动到指定目录
        os.makedirs("models", exist_ok=True)
        # 注意：ultralytics会自动缓存模型，这里不需要手动移动
        return True

    except Exception as e:
        logger.error(f"下载模型失败: {e}")
        return False


def run_cli_mode():
    """运行命令行模式"""
    print("\n" + "=" * 60)
    print("动物识别系统B端 - 命令行模式")
    print("=" * 60)

    print(f"目标设备: {config.HOST}:{config.PORT}")
    print(f"模型: {config.MODEL_PATH}")
    print(f"日志级别: {config.LOG_LEVEL}")
    print("\n命令:")
    print("  connect    - 连接到树莓派")
    print("  start      - 开始视频流")
    print("  stop       - 停止视频流")
    print("  take       - 抓拍单张图片")
    print("  stats      - 显示统计信息")
    print("  export     - 导出数据")
    print("  quit       - 退出程序")
    print("-" * 60)

    import threading
    from utils import ImageProcessor

    frame_count = 0
    detections_count = 0

    def process_frame_callback(frame_data):
        """帧处理回调"""
        nonlocal frame_count, detections_count

        frame_count += 1

        # 解码图像
        image = ImageProcessor.decode_jpeg(frame_data)
        if image is None:
            return

        # 检测动物
        detections = animal_detector.detect_animals(image, frame_count)
        detections_count += len(detections)

        if detections:
            print(f"\r帧数: {frame_count}, 检测数: {detections_count}, "
                  f"最近检测: {[d.animal_name for d in detections]}", end="")

    # 连接网络
    print("\n正在连接...")
    if not network_manager.start():
        print("连接失败!")
        return

    # 注册回调
    client = network_manager.get_client()
    client.register_callback(process_frame_callback)

    # 开始流
    client.start_stream()

    # 命令行循环
    try:
        while True:
            cmd = input("\n> ").strip().lower()

            if cmd == 'quit' or cmd == 'exit':
                break
            elif cmd == 'connect':
                network_manager.start()
            elif cmd == 'disconnect':
                network_manager.stop()
            elif cmd == 'start':
                client.start_stream()
            elif cmd == 'stop':
                client.stop_stream()
            elif cmd == 'take':
                print("正在抓拍...")
                frame_data = client.capture_single_frame()
                if frame_data:
                    print("抓拍成功!")
                else:
                    print("抓拍失败!")
            elif cmd == 'stats':
                print(f"\n统计信息:")
                print(f"  接收帧数: {frame_count}")
                print(f"  检测总数: {detections_count}")

                model_stats = animal_detector.get_system_statistics()
                print(f"  模型处理帧数: {model_stats['frames_processed']}")
                print(f"  平均检测时间: {model_stats.get('avg_detection_time', 0):.3f}秒")

                network_stats = client.get_statistics()
                print(f"  网络接收字节: {network_stats.get('bytes_received', 0)}")
                print(f"  队列大小: {network_stats.get('queue_size', 0)}")
            elif cmd == 'export':
                filename = input("导出文件名 (默认: export.json): ").strip()
                if not filename:
                    filename = "export.json"

                if filename.endswith('.csv'):
                    db_manager.export_to_csv(filename)
                else:
                    db_manager.export_to_json(filename)
                print(f"数据已导出到: {filename}")
            elif cmd == 'help':
                print("\n可用命令:")
                print("  connect    - 连接到树莓派")
                print("  start      - 开始视频流")
                print("  stop       - 停止视频流")
                print("  take       - 抓拍单张图片")
                print("  stats      - 显示统计信息")
                print("  export     - 导出数据")
                print("  quit       - 退出程序")
            else:
                print("未知命令，输入 'help' 查看可用命令")

    except KeyboardInterrupt:
        print("\n正在退出...")

    finally:
        cleanup()


def run_gui_mode():
    """运行GUI模式"""
    from display_gui import main as gui_main
    gui_main()


def export_data(filename: str):
    """导出数据"""
    if not filename:
        print("请指定导出文件名")
        return

    if filename.endswith('.csv'):
        db_manager.export_to_csv(filename)
    else:
        # 默认JSON
        if not filename.endswith('.json'):
            filename += '.json'
        db_manager.export_to_json(filename)

    print(f"数据已导出到: {filename}")


def cleanup():
    """清理资源"""
    logger.info("正在清理资源...")

    # 关闭网络连接
    network_manager.stop()

    # 关闭动物检测器
    animal_detector.close()

    logger.info("资源清理完成")


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()

    # 更新配置
    if args.host != config.HOST:
        config.HOST = args.host
        logger.info(f"更新目标主机为: {config.HOST}")

    if args.port != config.PORT:
        config.PORT = args.port
        logger.info(f"更新端口为: {config.PORT}")

    if args.model != config.MODEL_PATH:
        config.MODEL_PATH = args.model
        logger.info(f"更新模型路径为: {config.MODEL_PATH}")

    # 设置日志级别
    logger.setLevel(args.log_level.upper())
    for handler in logger.handlers:
        handler.setLevel(args.log_level.upper())

    # 设置信号处理器
    setup_signal_handlers()

    # 初始化系统
    initialize_system()

    # 处理导出命令
    if args.export:
        export_data(args.export)
        return

    # 运行模式选择
    try:
        if args.nogui:
            run_cli_mode()
        else:
            run_gui_mode()
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        raise
    finally:
        cleanup()


if __name__ == '__main__':
    main()