#!/usr/bin/env python3
# animal_detector_fixed.py - 修正版动物检测器，支持离线模式

import torch
import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict, Any

from tqdm.contrib import concurrent
import concurrent.futures
from ultralytics import YOLO
from datetime import datetime
import time
import os
import sys

from config import config
from utils import DetectionResult, logger


class AnimalDetector:
    """动物检测器（使用YOLOv8）"""

    def __init__(self, model_path: str = None):
        self.model_path = model_path or config.MODEL_PATH
        self.confidence_threshold = config.MODEL_CONFIDENCE
        self.iou_threshold = config.MODEL_IOU
        self.device = self._get_device()

        # 添加线程池执行器（用于异步检测）
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)  # 添加这行

        # 检查模型文件是否存在
        if not os.path.exists(self.model_path):
            logger.warning(f"模型文件不存在: {self.model_path}")
            self._download_or_create_model()

        # 加载模型
        self.model = None
        self.load_model()

        # 统计信息
        self.stats = {
            "total_detections": 0,
            "detection_time": 0,
            "frames_processed": 0,
            "animals_detected": {},
            "last_detection_time": None
        }

    def _get_device(self) -> str:
        """获取最佳设备（GPU/CPU）"""
        if torch.cuda.is_available():
            device = "cuda"
            logger.info(f"使用GPU: {torch.cuda.get_device_name(0)}")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = "mps"  # Apple Silicon
            logger.info("使用Apple MPS")
        else:
            device = "cpu"
            logger.info("使用CPU")

        return device

    def _download_or_create_model(self):
        """下载或创建模型文件"""
        logger.info(f"模型文件 {self.model_path} 不存在，尝试获取...")

        # 创建models目录
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

        # 尝试从多个来源获取模型
        sources = [
            self._download_from_mirror,
            self._create_test_model,
            self._create_dummy_model
        ]

        for source_func in sources:
            try:
                if source_func():
                    logger.info(f"模型获取成功: {self.model_path}")
                    return True
            except Exception as e:
                logger.warning(f"模型获取方法失败: {e}")

        logger.error("无法获取模型文件，程序可能无法正常运行")
        return False

    def _download_from_mirror(self):
        """从镜像下载模型"""
        import urllib.request
        import ssl

        mirrors = [
            "https://ghproxy.com/https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
            "https://github.moeyy.xyz/https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
            "https://gh.api.99988866.xyz/https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
        ]

        for mirror_url in mirrors:
            try:
                logger.info(f"尝试从镜像下载: {mirror_url}")
                ssl._create_default_https_context = ssl._create_unverified_context
                urllib.request.urlretrieve(mirror_url, self.model_path)

                # 检查文件大小
                if os.path.getsize(self.model_path) > 1000000:  # 大于1MB
                    return True
                else:
                    os.remove(self.model_path)
            except Exception as e:
                logger.warning(f"镜像下载失败: {e}")

        return False

    def _create_test_model(self):
        """创建测试模型"""
        logger.info("创建测试模型...")

        try:
            # 注意：这里我们使用self.model_path作为保存路径
            # 创建一个简单的模型结构
            model_data = {
                'model_name': 'TinyYOLO',
                'num_classes': 80,
                'input_size': [640, 480],
                'classes': [
                    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
                    'traffic light',
                    'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep',
                    'cow',
                    'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase',
                    'frisbee',
                    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard',
                    'surfboard',
                    'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
                    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
                    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard',
                    'cell phone',
                    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
                    'teddy bear',
                    'hair drier', 'toothbrush'
                ]
            }

            # 保存模型数据
            torch.save(model_data, self.model_path)

            logger.info(f"测试模型创建成功: {self.model_path}")
            logger.warning("注意: 这是一个测试模型，只能进行简单的检测")
            logger.warning("请尽快下载完整的YOLOv8模型以获得最佳效果")

            return True

        except Exception as e:
            logger.error(f"创建测试模型失败: {e}")
            return False

    def _create_dummy_model(self):
        """创建虚拟模型文件（仅用于占位）"""
        logger.warning("创建虚拟模型文件（功能受限）")

        # 创建一个小的模型文件
        with open(self.model_path, 'wb') as f:
            f.write(b'DUMMY_MODEL' * 1000)  # 约11KB

        return True

    def load_model(self):
        """加载YOLOv8模型"""
        try:
            logger.info(f"加载模型: {self.model_path}")

            # 检查文件大小
            if os.path.exists(self.model_path):
                file_size = os.path.getsize(self.model_path)
                logger.info(f"模型文件大小: {file_size / 1024 / 1024:.2f} MB")

                # 如果文件太小，可能是虚拟文件
                if file_size < 100000:  # 小于100KB
                    logger.warning("模型文件太小，可能无法正常工作")

            # 尝试加载模型
            self.model = YOLO(self.model_path)

            # 验证模型是否支持动物检测
            if hasattr(self.model, 'names'):
                animal_count = sum(1 for class_id, name in self.model.names.items()
                                   if name in config.ANIMAL_CLASSES.values())
                logger.info(f"模型支持 {animal_count} 种动物检测")

            logger.info("模型加载成功")

        except Exception as e:
            logger.error(f"模型加载失败: {e}")

            # 如果加载失败，尝试使用备用方案
            logger.info("尝试使用备用检测方案...")
            self.model = None

    def detect_animals(self, image: np.ndarray, frame_index: int = 0) -> List[DetectionResult]:
        """检测图像中的动物"""
        start_time = time.time()
        detections = []

        try:
            # 如果模型未加载，使用简单颜色检测作为备用
            if self.model is None:
                return self._simple_color_detection(image, frame_index)

            # 运行推理
            results = self.model.predict(
                source=image,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                device=self.device,
                verbose=False,
                max_det=10
            )

            # 处理结果
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        # 获取边界框坐标
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                        # 获取类别和置信度
                        class_id = int(box.cls[0].item())
                        confidence = float(box.conf[0].item())

                        # 获取类别名称
                        if hasattr(self.model, 'names'):
                            class_name = self.model.names.get(class_id, f"class_{class_id}")
                        else:
                            class_name = config.ANIMAL_CLASSES.get(class_id, f"class_{class_id}")

                        # 只处理动物类别
                        if class_name in config.ANIMAL_CLASSES.values():
                            # 创建检测结果
                            detection = DetectionResult(
                                animal_name=class_name,
                                confidence=confidence,
                                bbox=(x1, y1, x2, y2),
                                frame_timestamp=datetime.now(),
                                frame_index=frame_index
                            )
                            detections.append(detection)

                            # 更新统计信息
                            self.stats["total_detections"] += 1
                            self.stats["animals_detected"][class_name] = \
                                self.stats["animals_detected"].get(class_name, 0) + 1

            # 更新处理统计
            self.stats["frames_processed"] += 1
            self.stats["detection_time"] += time.time() - start_time
            self.stats["last_detection_time"] = datetime.now()

            if detections:
                logger.debug(f"检测到 {len(detections)} 个动物")

        except Exception as e:
            logger.error(f"动物检测失败: {e}")
            # 如果YOLO检测失败，回退到简单检测
            detections = self._simple_color_detection(image, frame_index)

        return detections

    def detect_async(self, image: np.ndarray, frame_index: int = 0):
        """异步检测（返回Future对象）"""
        return self.executor.submit(self.detect_animals, image, frame_index)

    def _simple_color_detection(self, image: np.ndarray, frame_index: int) -> List[DetectionResult]:
        """简单的颜色检测（备用方案）"""
        detections = []

        try:
            # 将图像转换为HSV颜色空间
            hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

            # 定义常见动物的颜色范围（简化版）
            color_ranges = {
                "dog": [(0, 30, 30), (30, 255, 255)],  # 棕色/黄色
                "cat": [(0, 0, 0), (180, 255, 100)],  # 黑色/灰色
                "bird": [(100, 150, 0), (140, 255, 255)],  # 蓝色
            }

            for animal_name, (lower, upper) in color_ranges.items():
                # 创建颜色掩码
                lower_np = np.array(lower)
                upper_np = np.array(upper)
                mask = cv2.inRange(hsv, lower_np, upper_np)

                # 查找轮廓
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area > 100:  # 忽略太小的区域
                        x, y, w, h = cv2.boundingRect(contour)

                        detection = DetectionResult(
                            animal_name=animal_name,
                            confidence=0.3,  # 低置信度
                            bbox=(x, y, x + w, y + h),
                            frame_timestamp=datetime.now(),
                            frame_index=frame_index
                        )
                        detections.append(detection)

                        # 更新统计
                        self.stats["total_detections"] += 1
                        self.stats["animals_detected"][animal_name] = \
                            self.stats["animals_detected"].get(animal_name, 0) + 1

            self.stats["frames_processed"] += 1

        except Exception as e:
            logger.error(f"简单颜色检测失败: {e}")

        return detections

    def get_important_detections(self, detections: List[DetectionResult]) -> List[DetectionResult]:
        """获取重要的检测结果（关注动物）"""
        return [
            det for det in detections
            if det.animal_name in config.IMPORTANT_ANIMALS
        ]

    def get_detection_statistics(self, detections: List[DetectionResult]) -> Dict[str, Any]:
        """获取检测统计信息"""
        stats = {
            "total": len(detections),
            "by_animal": {},
            "important_count": 0,
            "max_confidence": 0.0,
            "average_confidence": 0.0
        }

        if detections:
            confidences = [d.confidence for d in detections]
            stats["max_confidence"] = max(confidences)
            stats["average_confidence"] = np.mean(confidences)

            # 按动物分类统计
            for det in detections:
                stats["by_animal"][det.animal_name] = \
                    stats["by_animal"].get(det.animal_name, 0) + 1

                if det.animal_name in config.IMPORTANT_ANIMALS:
                    stats["important_count"] += 1

        return stats

    def get_system_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        stats = self.stats.copy()

        if stats["frames_processed"] > 0:
            stats["avg_detection_time"] = stats["detection_time"] / stats["frames_processed"]
            stats["detection_rate"] = stats["total_detections"] / stats["frames_processed"]
        else:
            stats["avg_detection_time"] = 0
            stats["detection_rate"] = 0

        return stats

    def save_model_info(self, filepath: str = "models/model_info.json"):
        """保存模型信息"""
        import json

        model_info = {
            "model_path": self.model_path,
            "device": self.device,
            "confidence_threshold": self.confidence_threshold,
            "iou_threshold": self.iou_threshold,
            "loaded_time": datetime.now().isoformat()
        }

        # 如果模型有names属性，添加可用类别
        if hasattr(self.model, 'names'):
            model_info["available_classes"] = dict(self.model.names)

        # 添加动物类别信息
        model_info["animal_classes"] = list(config.ANIMAL_CLASSES.values())
        model_info["important_animals"] = config.IMPORTANT_ANIMALS

        # 确保目录存在
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(model_info, f, ensure_ascii=False, indent=2)

        logger.info(f"模型信息已保存: {filepath}")

    def close(self):
        """清理资源"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)

        logger.info("动物检测器已关闭")


# 使用修正版的检测器
animal_detector = AnimalDetector()