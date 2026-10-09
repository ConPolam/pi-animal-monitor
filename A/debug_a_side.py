#!/usr/bin/env python3
# debug_a_side.py - 调试A端摄像头和响应

import subprocess
import time
import os


def check_camera():
    """检查摄像头状态"""
    print("=" * 60)
    print("检查摄像头状态")
    print("=" * 60)

    # 检查摄像头设备
    camera_devices = []
    for i in range(10):
        device = f"/dev/video{i}"
        if os.path.exists(device):
            camera_devices.append(device)

    print(f"找到摄像头设备: {camera_devices}")

    # 检查正在使用摄像头的进程
    print("\n检查正在使用摄像头的进程:")
    try:
        result = subprocess.run(['fuser', '-v', '/dev/video0'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print("摄像头被以下进程使用:")
            print(result.stdout)
        else:
            print("摄像头当前未被使用")
    except:
        pass

    return len(camera_devices) > 0


def test_capture():
    """测试摄像头捕获"""
    print("\n" + "=" * 60)
    print("测试摄像头捕获")
    print("=" * 60)

    test_methods = [
        ("v4l2-ctl 测试", ["v4l2-ctl", "--device=/dev/video0",
                           "--set-fmt-video=width=640,height=480,pixelformat=YUYV",
                           "--stream-mmap", "--stream-to=test_capture.yuv",
                           "--stream-count=1"]),
        ("fswebcam 测试", ["fswebcam", "-d", "/dev/video0", "-r", "640x480",
                           "--no-banner", "test_capture.jpg"]),
    ]

    for method_name, command in test_methods:
        print(f"\n测试: {method_name}")
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"  ✓ 成功")

                # 检查文件
                if "yuv" in command[0]:
                    if os.path.exists("test_capture.yuv"):
                        size = os.path.getsize("test_capture.yuv")
                        print(f"  文件大小: {size} 字节")
                        expected = 640 * 480 * 2  # YUYV格式
                        if size == expected:
                            print(f"  ✓ 文件大小正确")
                        else:
                            print(f"  ⚠ 文件大小异常 (期望 {expected}, 实际 {size})")
                elif "jpg" in command[0]:
                    if os.path.exists("test_capture.jpg"):
                        size = os.path.getsize("test_capture.jpg")
                        print(f"  文件大小: {size} 字节")
                        if size > 1000:
                            print(f"  ✓ JPEG文件有效")
                        else:
                            print(f"  ⚠ JPEG文件可能无效")
            else:
                print(f"  ✗ 失败: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"  ✗ 超时")
        except Exception as e:
            print(f"  ✗ 异常: {e}")

    return True


def check_a_program():
    """检查A端程序"""
    print("\n" + "=" * 60)
    print("检查A端程序")
    print("=" * 60)

    # 检查程序是否存在
    program_path = "./cam_sender"
    if not os.path.exists(program_path):
        print(f"✗ A端程序不存在: {program_path}")
        return False

    # 检查文件权限
    import stat
    st = os.stat(program_path)
    if not (st.st_mode & stat.S_IXUSR):
        print(f"✗ A端程序没有执行权限")
        print(f"  运行: chmod +x {program_path}")
        return False

    print(f"✓ A端程序存在且有执行权限")

    # 检查依赖
    print("\n检查依赖:")
    try:
        result = subprocess.run(["ldd", program_path], capture_output=True, text=True)
        if result.returncode == 0:
            print("动态库依赖:")
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"  {line}")
        else:
            print("无法检查依赖")
    except Exception as e:
        print(f"检查依赖失败: {e}")

    return True


def restart_a_program():
    """重启A端程序"""
    print("\n" + "=" * 60)
    print("重启A端程序")
    print("=" * 60)

    # 杀死正在运行的cam_sender进程
    try:
        subprocess.run(["pkill", "-f", "cam_sender"],
                       capture_output=True, text=True)
        print("已停止正在运行的cam_sender进程")
        time.sleep(1)
    except:
        pass

    # 启动新的cam_sender进程
    print("\n启动cam_sender...")
    try:
        # 使用nohup在后台运行
        process = subprocess.Popen(
            ["./cam_sender"],
            stdout=open("cam_sender.log", "w"),
            stderr=subprocess.STDOUT
        )

        print(f"cam_sender已启动 (PID: {process.pid})")
        print("等待3秒让程序初始化...")
        time.sleep(3)

        # 检查是否在运行
        if process.poll() is None:
            print("✓ cam_sender正在运行")

            # 检查日志
            if os.path.exists("cam_sender.log"):
                with open("cam_sender.log", "r") as f:
                    lines = f.readlines()
                    if lines:
                        print("\n程序输出:")
                        for line in lines[-5:]:  # 显示最后5行
                            print(f"  {line.strip()}")
        else:
            print("✗ cam_sender启动失败")
            return False

        return True

    except Exception as e:
        print(f"✗ 启动cam_sender失败: {e}")
        return False


def main():
    """主函数"""
    print("A端调试工具")
    print("=" * 60)

    # 1. 检查摄像头
    if not check_camera():
        print("✗ 摄像头检查失败")
        return False

    # 2. 测试摄像头捕获
    test_capture()

    # 3. 检查A端程序
    if not check_a_program():
        return False

    # 4. 重启A端程序
    if restart_a_program():
        print("\n" + "=" * 60)
        print("✓ A端调试完成")
        print("=" * 60)

        print("\n接下来:")
        print("1. 在PC端重新测试连接")
        print("2. 如果还有问题，检查日志: cam_sender.log")
        print("3. 查看树莓派系统日志: dmesg | tail -20")

        return True
    else:
        print("\n✗ A端重启失败")
        return False


if __name__ == "__main__":
    main()