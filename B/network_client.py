#!/usr/bin/env python3
# network_client.py - 网络通信客户端
import datetime
import socket
import struct
import threading
import time
import queue
from typing import Optional, Tuple, List, Callable
import numpy as np
from config import config
from utils import logger


class CameraClient:
    """摄像头客户端（连接树莓派A端）"""

    def __init__(self, host: str = None, port: int = None):
        self.host = host or config.HOST
        self.port = port or config.PORT
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.receiving = False
        self.frame_queue = queue.Queue(maxsize=100)  # 图像帧队列
        self.callbacks = []  # 回调函数列表
        self.threads = []

        # 统计信息
        self.stats = {
            "frames_received": 0,
            "bytes_received": 0,
            "connection_time": None,
            "last_frame_time": None
        }

    def connect(self) -> bool:
        """连接到树莓派A端"""
        try:
            logger.info(f"尝试连接到 {self.host}:{self.port}")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(config.CONNECT_TIMEOUT)
            self.socket.connect((self.host, self.port))
            self.connected = True
            self.stats["connection_time"] = time.time()
            logger.info("连接成功")
            return True
        except Exception as e:
            logger.error(f"连接失败: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            self.send_command("STOP")  # 先停止流
            time.sleep(0.1)
            self.socket.close()
            self.socket = None
        self.connected = False
        self.receiving = False
        logger.info("连接已断开")

    def send_command(self, command: str) -> bool:
        """发送控制命令"""
        if not self.connected or not self.socket:
            logger.warning("未连接，无法发送命令")
            return False

        try:
            # 命令以换行符结束
            cmd_bytes = f"{command}\n".encode('utf-8')
            self.socket.sendall(cmd_bytes)
            logger.info(f"命令发送成功: {command}")
            return True
        except Exception as e:
            logger.error(f"发送命令失败: {e}")
            return False

    def start_stream(self) -> bool:
        """开始接收视频流"""
        if not self.connected:
            if not self.connect():
                return False

        success = self.send_command("START")
        if success:
            self.receiving = True
            # 启动接收线程
            receive_thread = threading.Thread(target=self._receive_frames, daemon=True)
            receive_thread.start()
            self.threads.append(receive_thread)
            logger.info("开始接收视频流")

        return success

    def stop_stream(self) -> bool:
        """停止接收视频流"""
        success = self.send_command("STOP")
        if success:
            self.receiving = False
            logger.info("停止接收视频流")

        return success

    def capture_single_frame(self) -> Optional[bytes]:
        """捕获单张图片 - 先接收4字节长度头，再接收图片数据"""
        if not self.connected or not self.socket:
            logger.warning("未连接，无法抓拍")
            return None

        logger.info("开始抓拍...")

        try:
            # 保存原始超时设置
            original_timeout = self.socket.gettimeout()

            # ============ 步骤1: 发送TAKE命令 ============
            logger.info("发送TAKE命令...")
            self.socket.settimeout(5.0)

            # 先清空缓冲区（可选，但可能帮助）
            self._clear_socket_buffer_safely()

            # 发送命令
            self.socket.sendall(b"TAKE\n")

            # ============ 步骤2: 接收数据 ============
            logger.info("等待服务器响应...")
            self.socket.settimeout(10.0)

            # 方案一：直接接收数据块，然后从中解析长度头
            # 接收第一块数据（至少4字节，可能包含长度头）
            first_chunk = self.socket.recv(4096)
            logger.info(f"收到第一块数据: {len(first_chunk)} 字节")

            if len(first_chunk) < 4:
                logger.error(f"数据不足4字节: {len(first_chunk)} 字节")
                logger.debug(f"接收到的数据: {first_chunk.hex()}")
                self.socket.settimeout(original_timeout)
                return None

            # 尝试解析长度头
            length_data = first_chunk[:4]

            # 打印接收到的原始长度头
            logger.info(f"原始长度头数据: {length_data.hex()}")

            # 尝试多种字节序解析
            try:
                # 大端序（htonl的格式）
                data_length_be = struct.unpack('>I', length_data)[0]
                # 小端序
                data_length_le = struct.unpack('<I', length_data)[0]
                # 网络字节序（与大端序相同）
                data_length_net = struct.unpack('!I', length_data)[0]

                logger.info(f"大端序解析: {data_length_be} 字节")
                logger.info(f"小端序解析: {data_length_le} 字节")
                logger.info(f"网络字节序解析: {data_length_net} 字节")

                # 选择最合理的一个（38971在正常范围内）
                valid_range = (10000, 100000)  # 640x480 JPEG的合理范围

                for length, order in [
                    (data_length_be, "大端序"),
                    (data_length_le, "小端序"),
                    (data_length_net, "网络字节序")
                ]:
                    if valid_range[0] <= length <= valid_range[1]:
                        data_length = length
                        logger.info(f"使用{order}: {data_length} 字节")
                        break
                else:
                    # 如果都不在理想范围，选择最小的那个
                    candidates = [data_length_be, data_length_le, data_length_net]
                    # 过滤掉明显不合理的（过大）
                    reasonable = [c for c in candidates if c < 500000]
                    if reasonable:
                        data_length = min(reasonable)
                        logger.warning(f"使用最合理的值: {data_length} 字节")
                    else:
                        # 尝试直接在数据中寻找JPEG起始标记
                        logger.warning("所有解析都不合理，尝试在数据中查找JPEG...")

                        # 在整个数据块中查找JPEG起始标记
                        for i in range(len(first_chunk) - 1):
                            if first_chunk[i:i + 2] == b'\xff\xd8':
                                # 找到JPEG起始标记，从该位置开始就是JPEG数据
                                logger.info(f"在偏移 {i} 处找到JPEG起始标记")
                                jpeg_data = first_chunk[i:]

                                # 尝试找到JPEG结束标记
                                for j in range(len(jpeg_data) - 1, 1, -1):
                                    if jpeg_data[j - 1:j + 1] == b'\xff\xd9':
                                        logger.info(f"在偏移 {j - 1} 处找到JPEG结束标记")
                                        complete_jpeg = jpeg_data[:j + 1]

                                        # 验证是否合理大小
                                        if 10000 <= len(complete_jpeg) <= 500000:
                                            logger.info(f"提取到JPEG数据: {len(complete_jpeg)} 字节")
                                            self.socket.settimeout(original_timeout)
                                            return complete_jpeg

                                # 如果没有找到结束标记，返回找到的数据
                                logger.info(f"提取到不完整的JPEG数据: {len(jpeg_data)} 字节")
                                self.socket.settimeout(original_timeout)
                                return jpeg_data

                        logger.error("无法找到有效的JPEG数据")
                        self.socket.settimeout(original_timeout)
                        return None

            except struct.error as e:
                logger.error(f"解析长度头失败: {e}")
                # 尝试直接查找JPEG
                # ...（同上查找JPEG的代码）
                self.socket.settimeout(original_timeout)
                return None

            # ============ 步骤3: 接收剩余的图片数据 ============
            # 我们已经接收了4字节长度头，剩余的数据可能还在first_chunk中
            remaining_in_chunk = first_chunk[4:]  # 跳过长度头的部分

            # 计算还需要接收多少字节
            bytes_received = len(remaining_in_chunk)
            bytes_needed = data_length - bytes_received

            logger.info(f"已接收 {bytes_received}/{data_length} 字节，还需 {bytes_needed} 字节")

            image_data = remaining_in_chunk

            if bytes_needed > 0:
                # 接收剩余数据
                self.socket.settimeout(15.0)  # 设置较长超时

                try:
                    while bytes_received < data_length:
                        # 计算每次接收的大小
                        to_receive = min(8192, data_length - bytes_received)

                        chunk = self.socket.recv(to_receive)
                        if not chunk:
                            logger.error("连接中断")
                            break

                        image_data += chunk
                        bytes_received += len(chunk)

                        # 显示进度
                        if bytes_received % 20480 == 0:  # 每20KB
                            progress = (bytes_received / data_length) * 100
                            logger.info(f"已接收 {bytes_received}/{data_length} 字节 ({progress:.1f}%)")

                except socket.timeout:
                    logger.warning(f"接收超时，已接收 {bytes_received}/{data_length} 字节")

            # ============ 步骤4: 验证JPEG数据 ============
            logger.info(f"总共接收 {len(image_data)} 字节")

            if len(image_data) < 100:
                logger.error("接收的数据太少")
                self.socket.settimeout(original_timeout)
                return None

            # 验证JPEG起始标记
            if image_data[:2] != b'\xff\xd8':
                logger.warning(f"不是JPEG起始标记: {image_data[:2].hex()}")
                # 尝试查找JPEG起始标记
                for i in range(min(100, len(image_data) - 1)):
                    if image_data[i:i + 2] == b'\xff\xd8':
                        logger.info(f"在偏移 {i} 处找到JPEG起始标记，进行修正")
                        image_data = image_data[i:]
                        break

            # 验证JPEG结束标记
            if len(image_data) >= 2 and image_data[-2:] != b'\xff\xd9':
                logger.warning("JPEG缺少结束标记")
                # 但仍然可能有效

            logger.info(f"抓拍成功: {len(image_data)} 字节")
            self.socket.settimeout(original_timeout)
            return image_data

        except socket.timeout as e:
            logger.error(f"抓拍超时: {e}")
            return None
        except ConnectionError as e:
            logger.error(f"连接错误: {e}")
            self.connected = False
            return None
        except Exception as e:
            logger.error(f"抓拍过程中出现异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def _clear_socket_buffer_safely(self) -> int:
        """安全清空socket接收缓冲区（不改变socket设置）"""
        cleared = 0
        try:
            # 保存当前设置
            original_timeout = self.socket.gettimeout()

            # 设置为非阻塞，但只持续很短时间
            self.socket.settimeout(0.001)  # 1ms超时，基本相当于非阻塞

            for i in range(3):  # 最多尝试3次
                try:
                    while True:
                        data = self.socket.recv(65536)
                        if not data:
                            break
                        cleared += len(data)
                        if i == 0:  # 第一次清空时记录详细日志
                            logger.debug(f"清空缓冲区: 丢弃 {len(data)} 字节")
                except socket.timeout:
                    break  # 没有更多数据了
                except BlockingIOError:
                    break  # 非阻塞模式没有数据

            # 恢复原始设置
            self.socket.settimeout(original_timeout)

        except Exception as e:
            logger.warning(f"清空缓冲区失败: {e}")

        return cleared

    def _clear_socket_buffer_thoroughly(self):
        """彻底清空socket接收缓冲区"""
        cleared = 0
        try:
            # 保存原始设置
            original_timeout = self.socket.gettimeout()
            original_blocking = self.socket.getblocking()

            # 设置为非阻塞模式，清空缓冲区
            self.socket.setblocking(False)
            self.socket.settimeout(0)

            # 多次清空，确保彻底
            for i in range(5):
                try:
                    while True:
                        data = self.socket.recv(65536)
                        if not data:
                            break
                        cleared += len(data)
                        if i == 0:  # 只在第一轮记录详细日志
                            logger.debug(f"清空缓冲区: 丢弃 {len(data)} 字节")
                except (socket.error, BlockingIOError):
                    break

                # 短暂等待
                time.sleep(0.01)

            # 恢复原始设置
            self.socket.setblocking(original_blocking)
            self.socket.settimeout(original_timeout)

            if cleared > 0:
                logger.info(f"彻底清空了 {cleared} 字节的缓冲区数据")

        except Exception as e:
            logger.warning(f"清空缓冲区失败: {e}")

        return cleared

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """精确接收n字节数据"""
        data = b''
        start_time = time.time()

        while len(data) < n:
            try:
                remaining = n - len(data)
                chunk_size = min(8192, remaining)

                # 检查总超时
                if time.time() - start_time > 15:  # 15秒总超时
                    logger.error(f"接收数据总超时，已接收 {len(data)}/{n} 字节")
                    return None

                # 设置每次接收的超时
                timeout_left = 15 - (time.time() - start_time)
                if timeout_left <= 0:
                    logger.error("接收超时")
                    return None

                self.socket.settimeout(timeout_left)

                chunk = self.socket.recv(chunk_size)
                if not chunk:
                    logger.error(f"连接中断，已接收 {len(data)}/{n} 字节")
                    return None

                data += chunk

            except socket.timeout:
                logger.error(f"接收数据超时，已接收 {len(data)}/{n} 字节")
                return None
            except Exception as e:
                logger.error(f"接收数据出错: {e}")
                return None

        return data

    def _parse_and_validate_length(self, length_data: bytes) -> Optional[int]:
        """解析并验证长度头"""
        if len(length_data) != 4:
            logger.error(f"长度头数据不足4字节: {len(length_data)} 字节")
            return None

        # 尝试多种字节序
        try:
            # 大端序
            length_be = struct.unpack('>I', length_data)[0]
            # 小端序
            length_le = struct.unpack('<I', length_data)[0]
            # 网络字节序
            length_net = struct.unpack('!I', length_data)[0]

            # 合理范围：640x480 JPEG通常在10KB-80KB之间
            valid_range = (10000, 80000)

            for length, order in [(length_be, "大端序"), (length_le, "小端序"), (length_net, "网络字节序")]:
                if valid_range[0] <= length <= valid_range[1]:
                    logger.info(f"使用{order}: {length} 字节")
                    return length

            # 如果都不在理想范围，放宽条件
            extended_range = (5000, 200000)
            for length, order in [(length_be, "大端序"), (length_le, "小端序"), (length_net, "网络字节序")]:
                if extended_range[0] <= length <= extended_range[1]:
                    logger.warning(f"使用{order} (放宽范围): {length} 字节")
                    return length

            logger.error(f"所有解析都不合理: 大端={length_be}, 小端={length_le}, 网络={length_net}")
            return None

        except struct.error as e:
            logger.error(f"解析长度头失败: {e}")
            return None

    def _find_correct_length_in_stream(self, initial_data: bytes) -> Optional[int]:
        """在数据流中查找正确的长度头"""
        # 我们已经收到了4个字节，可能不是正确的长度头
        # 尝试在这个基础上接收更多数据，并在其中查找

        buffer = initial_data
        max_search_bytes = 1024  # 最多搜索1KB数据

        self.socket.settimeout(2.0)

        try:
            # 接收更多数据
            while len(buffer) < max_search_bytes:
                chunk = self.socket.recv(1024)
                if not chunk:
                    break
                buffer += chunk

                # 在缓冲区中搜索可能的长度头
                for i in range(len(buffer) - 3):
                    candidate = buffer[i:i + 4]
                    length = self._parse_and_validate_length(candidate)
                    if length is not None:
                        logger.info(f"在位置 {i} 找到有效的长度头: {length} 字节")

                        # 如果找到的位置不是0，说明前面有垃圾数据
                        if i > 0:
                            logger.warning(f"跳过 {i} 字节的垃圾数据")

                        # 丢弃找到位置之前的所有数据
                        # 注意：这里我们实际上已经接收了这些数据，但会在后续跳过
                        # 实际上，我们需要调整后续接收的逻辑
                        return length

        except socket.timeout:
            logger.warning("搜索长度头超时")

        logger.error(f"在 {len(buffer)} 字节数据中未找到有效的长度头")
        return None

    def _validate_jpeg_data(self, image_data: bytes) -> bool:
        """验证JPEG数据"""
        if len(image_data) < 100:  # 至少100字节
            logger.warning(f"数据量太小: {len(image_data)} 字节")
            return False

        # 检查JPEG起始标记
        if image_data[:2] != b'\xff\xd8':
            logger.warning(f"不是JPEG起始标记: {image_data[:2].hex()}")
            return False

        # 检查JPEG结束标记
        if image_data[-2:] != b'\xff\xd9':
            logger.warning("JPEG缺少结束标记")
            # 但仍然接受，因为可能传输不完整
            return len(image_data) > 10000  # 如果大于10KB，认为有效

        return True

    def _clear_socket_buffer(self):
        """清空socket接收缓冲区"""
        cleared = 0
        try:
            # 保存原始设置
            original_timeout = self.socket.gettimeout()
            original_blocking = self.socket.getblocking()

            # 设置为非阻塞模式，清空缓冲区
            self.socket.setblocking(False)
            self.socket.settimeout(0.1)

            try:
                # 多次尝试清空，确保彻底
                for i in range(3):
                    try:
                        while True:
                            data = self.socket.recv(65536)
                            if not data:
                                break
                            cleared += len(data)
                            logger.debug(f"清空缓冲区(第{i + 1}轮): 丢弃 {len(data)} 字节")
                    except (socket.error, BlockingIOError, socket.timeout):
                        break  # 没有更多数据了

                    # 短暂等待，看看是否有新数据
                    time.sleep(0.05)

            finally:
                # 恢复原始设置
                self.socket.setblocking(original_blocking)
                self.socket.settimeout(original_timeout)

        except Exception as e:
            logger.warning(f"清空缓冲区失败: {e}")

        return cleared

    def _clear_socket_buffer(self):
        """清空socket接收缓冲区"""
        cleared = 0
        try:
            # 保存原始设置
            original_timeout = self.socket.gettimeout()
            original_blocking = self.socket.getblocking()

            # 设置为非阻塞模式，清空缓冲区
            self.socket.setblocking(False)
            self.socket.settimeout(0.1)

            try:
                # 多次尝试清空，确保彻底
                for i in range(3):
                    try:
                        while True:
                            data = self.socket.recv(65536)
                            if not data:
                                break
                            cleared += len(data)
                            logger.debug(f"清空缓冲区(第{i + 1}轮): 丢弃 {len(data)} 字节")
                    except (socket.error, BlockingIOError, socket.timeout):
                        break  # 没有更多数据了

                    # 短暂等待，看看是否有新数据
                    time.sleep(0.05)

            finally:
                # 恢复原始设置
                self.socket.setblocking(original_blocking)
                self.socket.settimeout(original_timeout)

        except Exception as e:
            logger.warning(f"清空缓冲区失败: {e}")

        return cleared















    def _clear_socket_buffer_thoroughly(self):
        """彻底清空socket接收缓冲区"""
        cleared = 0
        try:
            # 保存原始设置
            original_timeout = self.socket.gettimeout()
            original_blocking = self.socket.getblocking()

            # 设置为非阻塞模式，多次清空
            self.socket.setblocking(False)
            self.socket.settimeout(0)

            # 多次尝试清空，确保没有残留数据
            for i in range(5):  # 尝试5次
                try:
                    while True:
                        data = self.socket.recv(65536)
                        if not data:
                            break
                        cleared += len(data)
                        logger.debug(f"清空缓冲区(第{i + 1}轮): 丢弃 {len(data)} 字节")
                except (socket.error, BlockingIOError):
                    break  # 没有更多数据了

                # 短暂等待，看看是否有新数据
                time.sleep(0.05)

            # 恢复原始设置
            self.socket.setblocking(original_blocking)
            self.socket.settimeout(original_timeout)

        except Exception as e:
            logger.warning(f"清空缓冲区失败: {e}")

        return cleared

    def _receive_length_header_with_validation(self):
        """接收并验证长度头，处理TCP粘包"""
        max_attempts = 10
        buffer = b''

        for attempt in range(max_attempts):
            try:
                # 接收数据
                chunk = self.socket.recv(4096)
                if not chunk:
                    logger.error(f"连接中断，尝试 {attempt + 1}/{max_attempts}")
                    return None

                buffer += chunk
                logger.debug(f"尝试 {attempt + 1}: 接收 {len(chunk)} 字节，总缓冲区 {len(buffer)} 字节")

                # 检查是否至少有4个字节
                if len(buffer) >= 4:
                    # 尝试提取长度头
                    for i in range(len(buffer) - 3):
                        # 取4个字节作为可能的长度头
                        candidate = buffer[i:i + 4]

                        # 尝试解析
                        length_be = struct.unpack('>I', candidate)[0]
                        length_le = struct.unpack('<I', candidate)[0]

                        # 检查哪个解析结果合理
                        if 1000 <= length_be <= 500000:
                            logger.info(f"找到合理的长度头(大端序): {length_be} 字节，位置: {i}")
                            # 移除前面的垃圾数据
                            buffer = buffer[i + 4:]
                            return candidate
                        elif 1000 <= length_le <= 500000:
                            logger.info(f"找到合理的长度头(小端序): {length_le} 字节，位置: {i}")
                            # 移除前面的垃圾数据
                            buffer = buffer[i + 4:]
                            return candidate

                # 如果没找到合理的长度头，继续接收
                if len(buffer) > 1000:  # 缓冲区太大，清空前1KB
                    logger.warning(f"缓冲区过大({len(buffer)}字节)，未找到长度头，丢弃前1KB")
                    buffer = buffer[1024:]

            except socket.timeout:
                logger.error(f"接收超时，尝试 {attempt + 1}/{max_attempts}")
                continue
            except struct.error:
                logger.warning(f"解包失败，尝试 {attempt + 1}/{max_attempts}")
                continue

        logger.error(f"经过 {max_attempts} 次尝试仍未找到合理的长度头")
        return None

    def _parse_length_header_safely(self, length_data):
        """安全解析长度头，尝试多种字节序"""
        if len(length_data) != 4:
            logger.error(f"长度头数据不足4字节: {len(length_data)} 字节")
            return None

        # 尝试多种字节序
        try:
            # 大端序
            length_be = struct.unpack('>I', length_data)[0]
            logger.debug(f"大端序解析: {length_be} 字节")

            # 小端序
            length_le = struct.unpack('<I', length_data)[0]
            logger.debug(f"小端序解析: {length_le} 字节")

            # 网络字节序
            length_net = struct.unpack('!I', length_data)[0]
            logger.debug(f"网络字节序解析: {length_net} 字节")

            # 主机字节序
            length_host = struct.unpack('I', length_data)[0]
            logger.debug(f"主机字节序解析: {length_host} 字节")

            # 选择合理的长度（640x480 JPEG通常在10KB-80KB之间）
            candidates = [length_be, length_le, length_net, length_host]
            for length in candidates:
                if 10000 <= length <= 80000:  # 合理的JPEG大小范围
                    logger.info(f"选择长度: {length} 字节")
                    return length

            # 如果没有在理想范围内，选择最接近合理范围的值
            for length in candidates:
                if 1000 <= length <= 500000:  # 放宽范围
                    logger.info(f"选择放宽范围的长度: {length} 字节")
                    return length

            logger.error(f"所有解析都不合理: {candidates}")
            return None

        except struct.error as e:
            logger.error(f"解析长度头失败: {e}")
            return None

    def _receive_image_data_reliably(self, data_length):
        """可靠地接收图片数据"""
        image_data = b''
        bytes_received = 0

        # 设置总超时
        start_time = time.time()

        while bytes_received < data_length:
            # 检查总超时
            if time.time() - start_time > 30:  # 30秒总超时
                logger.error(f"接收图片数据总超时，已接收 {bytes_received}/{data_length} 字节")
                return None

            try:
                # 计算剩余字节
                remaining = data_length - bytes_received
                chunk_size = min(8192, remaining)  # 8KB每次

                # 设置每次接收的超时
                self.socket.settimeout(5.0)

                chunk = self.socket.recv(chunk_size)
                if not chunk:
                    logger.error(f"连接中断，已接收 {bytes_received}/{data_length} 字节")
                    break

                image_data += chunk
                bytes_received += len(chunk)

                # 显示进度
                if bytes_received % 40960 == 0:  # 每40KB显示一次
                    progress = (bytes_received / data_length) * 100
                    logger.info(f"已接收 {bytes_received}/{data_length} 字节 ({progress:.1f}%)")

            except socket.timeout:
                # 如果已经接收了大部分数据，继续尝试
                if bytes_received > data_length * 0.9:
                    logger.info(f"接收基本完成 ({bytes_received}/{data_length})，可能略有误差")
                    break
                else:
                    logger.error(f"接收数据超时，已接收 {bytes_received}/{data_length} 字节")
                    return None

        logger.info(f"接收完成: {bytes_received}/{data_length} 字节")
        return image_data

    def _validate_jpeg_data(self, image_data):
        """验证JPEG数据"""
        if len(image_data) < 2:
            return False

        # 检查JPEG起始标记
        if image_data[:2] != b'\xff\xd8':
            logger.warning(f"不是JPEG起始标记: {image_data[:2].hex()}")
            return False

        # 检查JPEG结束标记
        if len(image_data) >= 2 and image_data[-2:] == b'\xff\xd9':
            return True

        # 如果没有结束标记，但数据看起来合理，也接受
        if len(image_data) > 10000:  # 至少10KB
            logger.warning("JPEG没有结束标记，但数据量看起来合理")
            return True

        return False





    def _quick_capture_with_new_connection(self):
        """使用新连接快速抓拍"""
        import socket
        import struct

        try:
            logger.info(f"创建新连接到 {config.HOST}:{config.PORT}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((config.HOST, config.PORT))
            logger.info("连接成功")

            # 发送TAKE命令
            logger.info("发送TAKE命令...")
            sock.sendall(b"TAKE\n")
            logger.info("TAKE命令已发送")

            # 接收长度头
            logger.info("等待长度头...")
            length_data = sock.recv(4)

            if len(length_data) != 4:
                logger.error(f"接收长度头失败: {len(length_data)}/4 字节")
                if length_data:
                    logger.error(f"接收到的数据: {length_data.hex()} (ASCII: {length_data})")
                sock.close()
                return None

            data_length = struct.unpack('>I', length_data)[0]
            logger.info(f"图片数据长度: {data_length} 字节")

            if data_length < 1000 or data_length > 500000:
                logger.error(f"数据长度不合理: {data_length} 字节")
                sock.close()
                return None

            # 接收图片数据
            logger.info(f"开始接收 {data_length} 字节的图片数据...")
            image_data = b''
            bytes_received = 0

            while bytes_received < data_length:
                to_receive = min(4096, data_length - bytes_received)
                chunk = sock.recv(to_receive)
                if not chunk:
                    logger.error("连接中断")
                    break
                image_data += chunk
                bytes_received += len(chunk)

                # 每接收10KB显示一次进度
                if bytes_received % 10240 == 0:
                    progress = (bytes_received / data_length) * 100
                    logger.debug(f"已接收 {bytes_received}/{data_length} 字节 ({progress:.1f}%)")

            sock.close()

            if bytes_received == data_length:
                logger.info(f"抓拍成功: {bytes_received} 字节")

                # 验证是否是有效的JPEG
                if len(image_data) >= 2 and image_data[:2] == b'\xff\xd8':
                    logger.info("验证: 是有效的JPEG文件")
                else:
                    logger.warning("警告: 数据可能不是有效的JPEG文件")

                return image_data
            else:
                logger.error(f"抓拍不完整: {bytes_received}/{data_length}")
                return None

        except socket.timeout:
            logger.error("抓拍超时")
            return None
        except Exception as e:
            logger.error(f"快速抓拍失败: {e}")
            return None
    def _receive_frames(self):
        """接收视频帧的线程函数"""
        buffer = b''
        expected_length = -1

        while self.receiving and self.connected:
            try:
                # 接收数据
                chunk = self.socket.recv(config.BUFFER_SIZE)
                if not chunk:
                    logger.warning("连接中断")
                    self.receiving = False
                    break

                buffer += chunk
                self.stats["bytes_received"] += len(chunk)

                # 处理缓冲区中的数据
                while len(buffer) >= 4:
                    # 如果还不知道期望的长度，尝试解析长度头
                    if expected_length == -1 and len(buffer) >= 4:
                        expected_length = struct.unpack('>I', buffer[:4])[0]
                        buffer = buffer[4:]

                    # 如果知道了期望长度，检查是否有足够的数据
                    if expected_length != -1 and len(buffer) >= expected_length:
                        # 提取一帧数据
                        frame_data = buffer[:expected_length]
                        buffer = buffer[expected_length:]

                        # 放入队列
                        if self.frame_queue.full():
                            self.frame_queue.get()  # 丢弃最旧的帧

                        self.frame_queue.put(frame_data)
                        self.stats["frames_received"] += 1
                        self.stats["last_frame_time"] = time.time()

                        # 通知回调函数
                        for callback in self.callbacks:
                            try:
                                callback(frame_data)
                            except Exception as e:
                                logger.error(f"回调函数执行失败: {e}")

                        # 重置期望长度
                        expected_length = -1
                    else:
                        # 数据不足，等待更多数据
                        break

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"接收帧时出错: {e}")
                self.receiving = False
                break

        logger.info("帧接收线程结束")

    def register_callback(self, callback: Callable[[bytes], None]):
        """注册回调函数，当接收到帧时调用"""
        self.callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[bytes], None]):
        """取消注册回调函数"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def get_next_frame(self, timeout: float = 1.0) -> Optional[bytes]:
        """从队列获取下一帧（阻塞）"""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = self.stats.copy()
        if stats["connection_time"]:
            stats["connection_duration"] = time.time() - stats["connection_time"]
        stats["queue_size"] = self.frame_queue.qsize()
        stats["callback_count"] = len(self.callbacks)
        return stats


class NetworkManager:
    """网络管理器"""

    def __init__(self):
        self.client = CameraClient()
        self.auto_reconnect = True
        self.reconnect_interval = 5  # 重连间隔（秒）

    def connect_with_retry(self, max_retries: int = 3) -> bool:
        """带重试的连接"""
        for attempt in range(max_retries):
            logger.info(f"连接尝试 {attempt + 1}/{max_retries}")
            if self.client.connect():
                return True
            time.sleep(self.reconnect_interval)
        return False

    def start(self) -> bool:
        """启动网络连接和视频流"""
        if not self.client.connected:
            if not self.connect_with_retry():
                return False

        return self.client.start_stream()

    def stop(self):
        """停止网络连接"""
        self.client.stop_stream()
        time.sleep(0.5)
        self.client.disconnect()

    def get_client(self) -> CameraClient:
        """获取客户端实例"""
        return self.client


# 全局网络管理器实例
network_manager = NetworkManager()