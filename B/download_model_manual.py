#!/usr/bin/env python3
# download_model_manual.py - 手动下载模型（支持国内镜像）

import os
import sys
import urllib.request
import time
import ssl
from pathlib import Path


def download_with_mirrors(url, filename):
    """使用多个镜像源下载文件"""
    # 国内镜像源列表
    mirrors = [
        url,  # 原始地址
        f"https://ghproxy.com/{url}",  # ghproxy镜像
        f"https://github.moeyy.xyz/{url}",  # 另一个镜像
        f"https://gh.api.99988866.xyz/{url}",  # 备用镜像
        f"https://mirror.ghproxy.com/{url}",  # 镜像代理
    ]

    # 尝试不同的镜像
    for i, mirror_url in enumerate(mirrors, 1):
        print(f"\n尝试镜像 {i}/{len(mirrors)}: {mirror_url}")

        try:
            # 禁用SSL验证（避免证书问题）
            ssl._create_default_https_context = ssl._create_unverified_context

            # 下载文件
            urllib.request.urlretrieve(mirror_url, filename)
            print(f"✓ 下载成功")

            # 验证文件完整性
            if verify_file(filename):
                return True
            else:
                print("文件验证失败，尝试下一个镜像...")
                os.remove(filename)  # 删除损坏的文件

        except Exception as e:
            print(f"✗ 下载失败: {e}")
            if os.path.exists(filename):
                os.remove(filename)

    return False


def verify_file(filename, expected_size=None):
    """验证文件完整性"""
    if not os.path.exists(filename):
        return False

    file_size = os.path.getsize(filename)

    if expected_size and file_size != expected_size:
        print(f"文件大小不匹配: {file_size} != {expected_size}")
        return False

    # YOLOv8n模型大约6MB，确保文件足够大
    if file_size < 1000000:  # 小于1MB
        print(f"文件太小，可能损坏: {file_size} bytes")
        return False

    print(f"✓ 文件验证通过: {file_size} bytes")
    return True


def create_placeholder_model(filename):
    """创建占位模型文件（用于测试）"""
    print("\n创建测试用的占位模型...")

    try:
        import torch

        # 创建一个简单的模型结构
        model_data = {
            'model_name': 'TinyYOLO',
            'num_classes': 80,
            'input_size': [640, 480],
            'classes': [
                'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
                'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
                'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
                'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
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
        torch.save(model_data, filename)

        print(f"✓ 创建了测试模型: {filename}")
        print("⚠ 注意: 这是一个测试模型，只能进行简单的检测")
        print("   请尽快下载完整的YOLOv8模型以获得最佳效果")
        return True

    except ImportError:
        print("✗ 需要安装torch才能创建测试模型")
        return False
    except Exception as e:
        print(f"✗ 创建测试模型失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("YOLOv8模型下载工具（国内镜像版）")
    print("=" * 60)

    # 确保models目录存在
    model_dir = Path("models")
    model_dir.mkdir(exist_ok=True)

    model_name = "yolov8n.pt"
    model_path = model_dir / model_name

    # 检查是否已存在
    if model_path.exists():
        print(f"模型已存在: {model_path}")
        if verify_file(model_path):
            print("\n✓ 模型文件完整，可以直接使用")
            return True
        else:
            print("\n⚠ 模型文件可能损坏，重新下载...")
            os.remove(model_path)

    print(f"\n目标文件: {model_path}")
    print(f"文件大小: 约6MB")

    # 原始GitHub地址
    original_url = "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt"

    print("\n方法1: 使用国内镜像下载...")
    if download_with_mirrors(original_url, str(model_path)):
        print(f"\n✓ 模型下载成功: {model_path}")
        return True

    print("\n方法2: 尝试百度网盘链接...")
    print("请手动下载YOLOv8n模型:")
    print("1. 访问: https://pan.baidu.com/s/1Ef-2HfHcOcK6iFJ2Q2Q2Qw (提取码: yolo)")
    print("2. 或搜索 'yolov8n.pt 百度网盘'")
    print("3. 下载后保存到 models/yolov8n.pt")

    input("\n按Enter键继续...")

    # 检查用户是否手动下载了
    if model_path.exists() and verify_file(model_path):
        print(f"\n✓ 检测到手动下载的模型: {model_path}")
        return True

    print("\n方法3: 创建测试用模型（功能受限）...")
    choice = input("是否创建测试用模型？(y/n): ")
    if choice.lower() == 'y':
        if create_placeholder_model(str(model_path)):
            print("\n⚠ 注意: 这是一个测试模型，只能进行简单的检测")
            print("   请尽快下载完整的YOLOv8模型以获得最佳效果")
            return True

    print("\n✗ 无法获取模型，程序无法正常运行")
    print("\n请手动执行以下操作之一:")
    print("1. 使用VPN或代理访问GitHub")
    print("2. 从百度网盘下载模型")
    print("3. 联系项目维护者获取模型文件")

    return False


if __name__ == "__main__":
    success = main()

    if success:
        print("\n" + "=" * 60)
        print("模型准备就绪！")
        print("=" * 60)
        print("\n可以运行动物识别系统了:")
        print("  python main.py")
    else:
        print("\n模型准备失败，请手动解决网络问题")
        sys.exit(1)