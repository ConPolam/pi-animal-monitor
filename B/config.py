#!/usr/bin/env python3
# config.py - 配置文件

import os
from dataclasses import dataclass, field
from typing import Tuple, List, Dict


@dataclass
class Config:
    """系统配置"""
    # 网络配置
    HOST: str = "192.168.137.158"  # 树莓派IP地址
    PORT: int = 5000
    BUFFER_SIZE: int = 4096
    CONNECT_TIMEOUT: int = 10

    # 图像处理配置
    IMAGE_WIDTH: int = 640
    IMAGE_HEIGHT: int = 480
    JPEG_QUALITY: int = 95
    FRAME_RATE: int = 10

    # 模型配置
    MODEL_PATH: str = "models/yolov8n.pt"
    MODEL_CONFIDENCE: float = 0.5
    MODEL_IOU: float = 0.45

    # 动物类别配置（COCO数据集）- 使用field的default_factory
    ANIMAL_CLASSES: Dict[int, str] = field(default_factory=lambda: {
        14: "bird", 15: "cat", 16: "dog", 17: "horse",
        18: "sheep", 19: "cow", 20: "elephant", 21: "bear",
        22: "zebra", 23: "giraffe"
    })

    # 重点关注动物 - 使用field的default_factory
    IMPORTANT_ANIMALS: List[str] = field(default_factory=lambda: ["cat", "dog", "bird", "horse", "cow"])

    # 数据库配置
    DATABASE_URL: str = "sqlite:///animal_detection.db"

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/animal_recognition.log"

    # 界面配置
    UI_THEME: str = "dark"  # dark/light
    UI_LANGUAGE: str = "zh"  # zh/en

    # 报警配置
    ALERT_ENABLED: bool = True
    ALERT_COOLDOWN: int = 30  # 报警冷却时间（秒）

    @classmethod
    def create_directories(cls):
        """创建必要的目录"""
        directories = ["models", "logs", "data", "screenshots", "videos"]
        for dir_name in directories:
            os.makedirs(dir_name, exist_ok=True)

    @classmethod
    def get_animal_color(cls, animal_name: str) -> Tuple[int, int, int]:
        """获取动物对应的显示颜色"""
        color_map = {
            "cat": (255, 105, 180),  # 粉色
            "dog": (255, 165, 0),  # 橙色
            "bird": (0, 191, 255),  # 深天蓝
            "horse": (139, 69, 19),  # 棕色
            "cow": (128, 128, 128),  # 灰色
            "sheep": (255, 255, 255),  # 白色
            "elephant": (192, 192, 192),  # 银色
            "bear": (139, 0, 0),  # 深红
            "zebra": (0, 0, 0),  # 黑色
            "giraffe": (218, 165, 32),  # 金色
        }
        return color_map.get(animal_name, (0, 255, 0))  # 默认绿色


config = Config()
config.create_directories()