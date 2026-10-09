#!/usr/bin/env python3
import socket
import struct
import cv2
import threading
import time

# =====================
# 配置部分
# =====================
HOST = '0.0.0.0'  # 本机监听所有网卡
PORT = 5000  # 发送端端口，可以和B约定
CAM_INDEX = 0  # 摄像头索引，0表示默认摄像头

# =====================
# 全局变量
# =====================
sending = False
streaming_thread = None
stop_streaming = threading.Event()

# =====================
# 打开摄像头
# =====================
cap = cv2.VideoCapture(CAM_INDEX)
if not cap.isOpened():
    print("摄像头打开失败，请检查摄像头是否连接")
    exit(1)
print("摄像头准备就绪")

# =====================
# 创建TCP服务端，等待B连接
# =====================
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((HOST, PORT))
s.listen(1)
print(f"等待B连接, IP={socket.gethostbyname(socket.gethostname())}, 端口={PORT} ...")
conn, addr = s.accept()
print(f"B已连接：{addr}")


# =====================
# 函数：接收控制命令
# =====================
def recv_command(conn):
    try:
        data = conn.recv(1024).decode()
        return data.strip()
    except:
        return ""


# =====================
# 函数：采集摄像头帧并压缩成JPEG
# =====================
def capture_frame(cap):
    ret, frame = cap.read()
    if not ret:
        return None
    ret, jpeg = cv2.imencode('.jpg', frame)
    if not ret:
        return None
    return jpeg.tobytes()


# =====================
# 函数：发送JPEG图像
# 协议： [4字节长度][JPEG数据]
# =====================
def send_frame(conn, jpeg_bytes):
    try:
        length = struct.pack('>I', len(jpeg_bytes))  # 4字节大端长度
        conn.sendall(length)
        conn.sendall(jpeg_bytes)
        return True
    except Exception as e:
        print(f"发送帧失败: {e}")
        return False


# =====================
# 函数：开始流媒体传输
# =====================
def start_streaming(conn, cap):
    """开始持续传输视频流"""
    global stop_streaming

    print("开始视频流传输...")
    stop_streaming.clear()

    frame_count = 0
    while not stop_streaming.is_set():
        try:
            frame = capture_frame(cap)
            if frame:
                if not send_frame(conn, frame):
                    break
                frame_count += 1
                if frame_count % 30 == 0:  # 每30帧打印一次
                    print(f"已发送 {frame_count} 帧")

                # 控制帧率，大约10fps
                time.sleep(0.1)
            else:
                print("无法捕获帧")
                break

        except Exception as e:
            print(f"流传输出错: {e}")
            break

    print("视频流传输停止")


# =====================
# 主循环
# =====================
try:
    while True:
        # 设置超时，以便能够定期检查连接状态
        conn.settimeout(0.5)

        try:
            cmd = recv_command(conn)
            if cmd:
                print(f"收到命令: {cmd}")

                if cmd == "TAKE":
                    print("执行抓拍...")
                    # 停止当前的流传输
                    if sending:
                        stop_streaming.set()
                        if streaming_thread:
                            streaming_thread.join(timeout=1)

                    # 抓拍一张照片
                    frame = capture_frame(cap)
                    if frame:
                        if send_frame(conn, frame):
                            print("已发送一张图片")
                        else:
                            print("发送图片失败，连接可能已断开")
                    else:
                        print("抓拍失败")

                    # 自动重新开始流传输
                    print("自动重新开始视频流...")
                    sending = True
                    stop_streaming.clear()
                    streaming_thread = threading.Thread(
                        target=start_streaming,
                        args=(conn, cap),
                        daemon=True
                    )
                    streaming_thread.start()

                elif cmd == "START":
                    if not sending:
                        print("开始视频流传输...")
                        sending = True
                        stop_streaming.clear()
                        streaming_thread = threading.Thread(
                            target=start_streaming,
                            args=(conn, cap),
                            daemon=True
                        )
                        streaming_thread.start()
                    else:
                        print("已经在传输视频流")

                elif cmd == "STOP":
                    if sending:
                        print("停止视频流传输...")
                        sending = False
                        stop_streaming.set()
                        if streaming_thread:
                            streaming_thread.join(timeout=1)
                    else:
                        print("当前没有传输视频流")

                elif cmd == "EXIT" or cmd == "QUIT":
                    print("收到退出命令")
                    break

        except socket.timeout:
            # 这是正常的超时，用于定期检查命令
            continue
        except Exception as e:
            print(f"接收命令时出错: {e}")
            break

except KeyboardInterrupt:
    print("程序被用户中断")
except Exception as e:
    print(f"程序出错: {e}")
finally:
    print("清理资源...")
    # 停止流传输
    stop_streaming.set()
    if streaming_thread:
        streaming_thread.join(timeout=1)

    # 关闭摄像头和连接
    cap.release()
    conn.close()
    s.close()
    print("程序结束")