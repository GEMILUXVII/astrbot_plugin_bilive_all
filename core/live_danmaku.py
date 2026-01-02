"""
Bilibili Live Danmaku WebSocket Client
Ported from StarBot's live.py - handles real-time event streaming
"""

import asyncio
import json
import random
import struct
import zlib
from collections.abc import Callable
from enum import Enum
from typing import Any

import aiohttp
import brotli

from ..utils.credential import credential_manager
from .live_room import LiveRoom


class Operation(Enum):
    """WebSocket 操作码"""
    HEARTBEAT = 2
    HEARTBEAT_REPLY = 3
    MESSAGE = 5
    USER_AUTHENTICATION = 7
    CONNECT_SUCCESS = 8


class LiveDanmaku:
    """
    Bilibili 直播弹幕 WebSocket 客户端

    连接到直播间并接收实时弹幕、礼物、SC 等事件
    """

    HEARTBEAT_INTERVAL = 30

    def __init__(self, room_id: int):
        """
        Args:
            room_id: 直播间房间号
        """
        self.room_display_id = room_id
        self.room_id: int | None = None

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._heartbeat_task: asyncio.Task | None = None

        self._handlers: dict[str, list[Callable]] = {}
        self._status = 0  # 0=未连接, 1=连接中, 2=已连接, 3=断开中
        self._auth_event = asyncio.Event()  # 用于等待认证完成

        self._live_room = LiveRoom(room_id)

    def get_status(self) -> int:
        """获取连接状态"""
        return self._status

    def on(self, event: str):
        """
        事件装饰器

        Args:
            event: 事件名称
                - LIVE: 开播
                - PREPARING: 下播
                - DANMU_MSG: 弹幕
                - SEND_GIFT: 礼物
                - SUPER_CHAT_MESSAGE: SC
                - GUARD_BUY: 大航海
                - VERIFICATION_SUCCESSFUL: 连接成功
        """
        def decorator(func: Callable):
            if event not in self._handlers:
                self._handlers[event] = []
            self._handlers[event].append(func)
            return func
        return decorator

    def dispatch(self, event: str, data: Any):
        """
        分发事件
        """
        if event in self._handlers:
            for handler in self._handlers[event]:
                asyncio.create_task(handler({"data": data}))

    async def connect(self):
        """连接到直播间"""
        from astrbot.api import logger

        if self._status != 0:
            logger.debug(f"[BiliLive-WS] 状态不为0，跳过连接: {self._status}")
            return

        self._status = 1

        try:
            logger.debug(f"[BiliLive-WS] 开始连接房间 {self.room_display_id}")

            # 获取真实房间号
            room_info = await self._live_room.get_room_play_info()
            self.room_id = room_info.get("room_id", self.room_display_id)
            logger.debug(f"[BiliLive-WS] 获取到真实房间号: {self.room_id}")

            # 获取弹幕服务器配置
            chat_conf = await self._live_room.get_chat_conf()
            host_list = chat_conf.get("host_list", [])
            token = chat_conf.get("token", "")

            logger.debug(f"[BiliLive-WS] 获取到 {len(host_list)} 个弹幕服务器")

            if not host_list:
                raise Exception("无法获取弹幕服务器地址")

            # 选择服务器
            host = random.choice(host_list)
            ws_url = f"wss://{host['host']}:{host['wss_port']}/sub"
            logger.info(f"[BiliLive-WS] 正在连接到 {ws_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Origin": "https://live.bilibili.com",
            }
            cookies = credential_manager.get_cookies()
            if cookies:
                cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                headers["Cookie"] = cookie_header

            # 建立连接 (必须添加 User-Agent，否则服务器会拒绝)
            # 设置较长的超时以防止连接被过早关闭
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=None)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._ws = await self._session.ws_connect(
                ws_url,
                headers=headers,
                # 不使用 aiohttp 内置心跳，Bilibili 使用自定义二进制心跳
                autoping=True,  # 响应 ping 帧
                autoclose=False,  # 不自动关闭
                receive_timeout=None,  # 不设置接收超时
            )
            logger.info("[BiliLive-WS] WebSocket 连接成功")

            # 发送认证包
            await self._send_auth(token)
            logger.debug("[BiliLive-WS] 已发送认证包")

            # 启动心跳
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 开始接收消息
            asyncio.create_task(self._receive_loop())
            logger.info(f"[BiliLive-WS] 房间 {self.room_id} 连接流程完成，等待认证响应")

        except Exception as e:
            logger.error(f"[BiliLive-WS] 连接房间 {self.room_display_id} 失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._status = 0
            if self._session:
                await self._session.close()
            raise e

    async def disconnect(self):
        """断开连接"""
        if self._status == 0:
            return

        self._status = 3

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()

        if self._session:
            await self._session.close()

        self._status = 0

    async def _send_auth(self, token: str):
        """发送认证包"""
        # 获取凭据中的 buvid3 和 uid
        credential = credential_manager.get_credential()
        buvid = ""
        uid = 0
        if credential:
            buvid = credential.buvid3 or ""
            try:
                uid = await credential_manager.get_uid()
            except Exception:
                uid = 0

        auth_data = {
            "uid": uid,
            "roomid": self.room_id,
            "protover": 3,
            "buvid": buvid,  # 必需字段
            "platform": "web",
            "type": 2,
            "key": token,
        }
        from astrbot.api import logger
        logger.debug(f"[BiliLive-WS] 认证数据: roomid={self.room_id}, buvid={buvid[:10]}..." if buvid else f"[BiliLive-WS] 认证数据: roomid={self.room_id}, buvid=空")
        await self._send_packet(Operation.USER_AUTHENTICATION, json.dumps(auth_data))

    async def _send_packet(self, operation: Operation, data: str = ""):
        """发送数据包"""
        if not self._ws:
            return

        body = data.encode("utf-8") if data else b""
        header = struct.pack(">IHHII", len(body) + 16, 16, 1, operation.value, 1)
        await self._ws.send_bytes(header + body)

    async def _heartbeat_loop(self):
        """心跳循环"""
        from astrbot.api import logger

        # 等待认证成功（状态变为 2）
        await self._auth_event.wait()

        logger.debug(f"[BiliLive-WS] 心跳任务开始，状态: {self._status}")

        while self._status == 2:
            await self._send_packet(Operation.HEARTBEAT, "")
            logger.debug("[BiliLive-WS] 发送心跳包")
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def _receive_loop(self):
        """接收消息循环"""
        from astrbot.api import logger
        logger.info(f"[BiliLive-WS] 开始接收消息循环 房间 {self.room_id}")

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    await self._parse_packet(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"[BiliLive-WS] WebSocket 错误: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSING:
                    logger.warning("[BiliLive-WS] WebSocket 正在关闭...")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    # 获取关闭码和原因
                    close_code = self._ws.close_code if self._ws else "unknown"
                    logger.warning(f"[BiliLive-WS] WebSocket 已关闭, 关闭码: {close_code}")
                    break
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    logger.debug(f"[BiliLive-WS] 收到文本消息: {msg.data[:100]}...")
        except asyncio.CancelledError:
            logger.info("[BiliLive-WS] 接收循环被取消")
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"[BiliLive-WS] 接收消息异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            from astrbot.api import logger
            close_code = self._ws.close_code if self._ws else "N/A"
            logger.warning(f"[BiliLive-WS] 接收循环结束，当前状态: {self._status}, 关闭码: {close_code}")
            if self._status == 2:
                # 意外断开，尝试重连
                self._status = 0
                await asyncio.sleep(5)
                await self.connect()

    async def _parse_packet(self, data: bytes):
        """解析数据包"""
        from astrbot.api import logger

        offset = 0
        while offset < len(data):
            # 解析包头
            packet_len, header_len, ver, operation, _ = struct.unpack(">IHHII", data[offset:offset + 16])
            body = data[offset + header_len:offset + packet_len]
            offset += packet_len

            if operation == Operation.CONNECT_SUCCESS.value:
                logger.info(f"[BiliLive-WS] 收到认证成功响应! 房间 {self.room_id}")
                self._status = 2
                self._auth_event.set()
                self.dispatch("VERIFICATION_SUCCESSFUL", {})

            elif operation == Operation.HEARTBEAT_REPLY.value:
                # 心跳回复，包含人气值
                if len(body) >= 4:
                    popularity = struct.unpack(">I", body[:4])[0]
                    self.dispatch("POPULARITY", {"popularity": popularity})

            elif operation == Operation.MESSAGE.value:
                # 普通消息
                if ver == 0 or ver == 1:
                    await self._parse_message(body)
                elif ver == 2:
                    # zlib 压缩
                    decompressed = zlib.decompress(body)
                    await self._parse_packet(decompressed)
                elif ver == 3:
                    # brotli 压缩
                    decompressed = brotli.decompress(body)
                    await self._parse_packet(decompressed)

    async def _parse_message(self, body: bytes):
        """解析消息体"""
        try:
            data = json.loads(body.decode("utf-8"))
            cmd = data.get("cmd", "")

            # 处理带后缀的命令（如 DANMU_MSG:4:0:2:2:2:0）
            if ":" in cmd:
                cmd = cmd.split(":")[0]

            # 分发事件
            self.dispatch(cmd, data)

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
