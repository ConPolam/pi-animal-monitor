#!/usr/bin/env python3
# database.py - 数据库模块

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
from typing import List, Dict, Any, Optional

from config import config
from utils import logger

Base = declarative_base()


class DetectionRecord(Base):
    """检测记录表"""
    __tablename__ = 'detections'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    animal_name = Column(String(50))
    confidence = Column(Float)
    bbox_x1 = Column(Integer)
    bbox_y1 = Column(Integer)
    bbox_x2 = Column(Integer)
    bbox_y2 = Column(Integer)
    frame_width = Column(Integer)
    frame_height = Column(Integer)
    frame_index = Column(Integer)
    image_path = Column(String(255))  # 保存的图像路径

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "animal_name": self.animal_name,
            "confidence": self.confidence,
            "bbox": [self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2],
            "frame_size": [self.frame_width, self.frame_height],
            "frame_index": self.frame_index,
            "image_path": self.image_path
        }


class SystemLog(Base):
    """系统日志表"""
    __tablename__ = 'system_logs'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    level = Column(String(20))  # INFO, WARNING, ERROR
    module = Column(String(50))
    message = Column(Text)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "level": self.level,
            "module": self.module,
            "message": self.message
        }


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or config.DATABASE_URL
        self.engine = create_engine(self.database_url, echo=False)
        self.Session = sessionmaker(bind=self.engine)

        # 创建表
        self.create_tables()

        logger.info(f"数据库连接成功: {self.database_url}")

    def create_tables(self):
        """创建数据库表"""
        Base.metadata.create_all(self.engine)

    def add_detection(self, animal_name: str, confidence: float, bbox: tuple,
                      frame_size: tuple, frame_index: int, image_path: str = None) -> DetectionRecord:
        """添加检测记录"""
        session = self.Session()
        try:
            record = DetectionRecord(
                animal_name=animal_name,
                confidence=confidence,
                bbox_x1=bbox[0],
                bbox_y1=bbox[1],
                bbox_x2=bbox[2],
                bbox_y2=bbox[3],
                frame_width=frame_size[0],
                frame_height=frame_size[1],
                frame_index=frame_index,
                image_path=image_path
            )

            session.add(record)
            session.commit()

            logger.debug(f"检测记录已保存: {animal_name}")
            return record

        except Exception as e:
            session.rollback()
            logger.error(f"保存检测记录失败: {e}")
            raise
        finally:
            session.close()

    def add_system_log(self, level: str, module: str, message: str) -> SystemLog:
        """添加系统日志"""
        session = self.Session()
        try:
            log = SystemLog(
                level=level,
                module=module,
                message=message
            )

            session.add(log)
            session.commit()

            return log

        except Exception as e:
            session.rollback()
            logger.error(f"保存系统日志失败: {e}")
            raise
        finally:
            session.close()

    def get_detections_by_animal(self, animal_name: str, limit: int = 100) -> List[DetectionRecord]:
        """按动物名称获取检测记录"""
        session = self.Session()
        try:
            records = session.query(DetectionRecord) \
                .filter(DetectionRecord.animal_name == animal_name) \
                .order_by(DetectionRecord.timestamp.desc()) \
                .limit(limit) \
                .all()

            return records
        finally:
            session.close()

    def get_detections_by_time_range(self, start_time: datetime, end_time: datetime) -> List[DetectionRecord]:
        """按时间范围获取检测记录"""
        session = self.Session()
        try:
            records = session.query(DetectionRecord) \
                .filter(DetectionRecord.timestamp.between(start_time, end_time)) \
                .order_by(DetectionRecord.timestamp.desc()) \
                .all()

            return records
        finally:
            session.close()

    def get_statistics(self, start_time: datetime = None, end_time: datetime = None) -> Dict[str, Any]:
        """获取统计信息"""
        session = self.Session()
        try:
            # 基础查询
            query = session.query(DetectionRecord)

            # 时间过滤
            if start_time:
                query = query.filter(DetectionRecord.timestamp >= start_time)
            if end_time:
                query = query.filter(DetectionRecord.timestamp <= end_time)

            # 总检测数
            total_detections = query.count()

            # 按动物分类统计
            animal_stats = {}
            for record in query.all():
                animal_name = record.animal_name
                if animal_name not in animal_stats:
                    animal_stats[animal_name] = {
                        "count": 0,
                        "avg_confidence": 0,
                        "total_confidence": 0
                    }

                animal_stats[animal_name]["count"] += 1
                animal_stats[animal_name]["total_confidence"] += record.confidence

            # 计算平均置信度
            for animal, stats in animal_stats.items():
                if stats["count"] > 0:
                    stats["avg_confidence"] = stats["total_confidence"] / stats["count"]

            # 最近检测
            recent_detections = query \
                .order_by(DetectionRecord.timestamp.desc()) \
                .limit(10) \
                .all()

            return {
                "total_detections": total_detections,
                "animal_statistics": animal_stats,
                "recent_detections": [rec.to_dict() for rec in recent_detections],
                "time_range": {
                    "start": start_time.isoformat() if start_time else None,
                    "end": end_time.isoformat() if end_time else None
                }
            }

        finally:
            session.close()

    def export_to_csv(self, filepath: str, start_time: datetime = None, end_time: datetime = None):
        """导出数据到CSV文件"""
        import pandas as pd

        session = self.Session()
        try:
            # 获取数据
            query = session.query(DetectionRecord)

            if start_time:
                query = query.filter(DetectionRecord.timestamp >= start_time)
            if end_time:
                query = query.filter(DetectionRecord.timestamp <= end_time)

            records = query.all()

            # 转换为DataFrame
            data = [rec.to_dict() for rec in records]
            df = pd.DataFrame(data)

            # 保存CSV
            df.to_csv(filepath, index=False, encoding='utf-8')
            logger.info(f"数据已导出到: {filepath}")

        finally:
            session.close()

    def export_to_json(self, filepath: str, start_time: datetime = None, end_time: datetime = None):
        """导出数据到JSON文件"""
        session = self.Session()
        try:
            # 获取统计数据
            stats = self.get_statistics(start_time, end_time)

            # 保存JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

            logger.info(f"数据已导出到: {filepath}")

        finally:
            session.close()

    def backup_database(self, backup_path: str):
        """备份数据库"""
        import shutil
        import sqlite3

        if self.database_url.startswith('sqlite:///'):
            db_path = self.database_url.replace('sqlite:///', '')
            shutil.copy2(db_path, backup_path)
            logger.info(f"数据库已备份到: {backup_path}")


# 全局数据库管理器实例
db_manager = DatabaseManager()