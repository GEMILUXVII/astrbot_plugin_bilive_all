"""
Room Monitor - Combines WebSocket connection with event handling
Handles live events (start/end) and collects statistics
"""

import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Awaitable, TYPE_CHECKING

from astrbot.api import logger

from .live_danmaku import LiveDanmaku
from .live_room import LiveRoom, get_room_id_by_uid
from .models import RoomConfig, LiveReport
from ..storage.stats_db import StatsDB

if TYPE_CHECKING:
    from ..main import BiliLivePlugin


class RoomMonitor:
    """
    房间监控器
    
    负责：
    - 连接直播间 WebSocket
    - 处理开播/下播事件
    - 收集弹幕/礼物/SC/大航海统计
    - 触发报告生成
    """
    
    # 断线重连间隔阈值（秒）
    RECONNECT_THRESHOLD = 60
    
    def __init__(
        self,
        config: RoomConfig,
        db: StatsDB,
        on_live_start: Optional[Callable[["RoomMonitor", Dict], Awaitable]] = None,
        on_live_end: Optional[Callable[["RoomMonitor", Dict], Awaitable]] = None,
    ):
        """
        Args:
            config: 房间配置
            db: 统计数据库
            on_live_start: 开播回调
            on_live_end: 下播回调
        """
        self.config = config
        self.db = db
        self._on_live_start = on_live_start
        self._on_live_end = on_live_end
        
        self.room_id: Optional[int] = config.room_id
        self.uname: Optional[str] = config.uname
        
        self._danmaku: Optional[LiveDanmaku] = None
        self._live_room: Optional[LiveRoom] = None
        self._connecting = False
        self._is_reconnect = False
        self._last_live_push_time: Optional[int] = None
        
        # 防止重复 LIVE 事件处理的锁
        self._live_event_lock = asyncio.Lock()
        # 内存中的直播状态标志（用于快速去重）
        self._is_live = False
    
    @property
    def uid(self) -> int:
        return self.config.uid
    
    @property
    def status(self) -> int:
        """获取连接状态"""
        return self._danmaku.get_status() if self._danmaku else 0
    
    async def connect(self):
        """连接到直播间"""
        if self._connecting:
            logger.warning(f"[BiliLive] {self.uname or self.uid} 正在连接中，跳过")
            return False
        
        self._connecting = True
        
        try:
            # 如果没有 room_id，通过 UID 获取
            if not self.room_id:
                logger.info(f"[BiliLive] 正在通过 UID {self.config.uid} 获取直播间信息...")
                user_info = await get_room_id_by_uid(self.config.uid)
                
                self.room_id = user_info.get("room_id")
                self.uname = user_info.get("uname") or f"UID:{self.config.uid}"
                
                if not self.room_id:
                    logger.error(f"[BiliLive] 用户 {self.uname} ({self.config.uid}) 没有直播间")
                    return False
                
                logger.info(f"[BiliLive] 获取到 {self.uname} 的直播间: {self.room_id}")
            
            # 如果没有 uname，获取用户信息
            if not self.uname:
                user_info = await get_room_id_by_uid(self.config.uid)
                self.uname = user_info.get("uname") or f"UID:{self.config.uid}"
            
            # 创建 WebSocket 客户端
            self._danmaku = LiveDanmaku(self.room_id)
            self._live_room = LiveRoom(self.room_id)
            
            # 注册事件处理器
            self._register_handlers()
            
            logger.info(f"[BiliLive] 准备连接到 {self.uname} 的直播间 {self.room_id}")
            
            # 连接
            await self._danmaku.connect()
            
            return True
            
        except Exception as e:
            logger.error(f"[BiliLive] 连接 {self.uname} 失败: {e}")
            return False
        finally:
            self._connecting = False
    
    async def disconnect(self):
        """断开连接"""
        if self._danmaku:
            await self._danmaku.disconnect()
            logger.info(f"[BiliLive] 已断开 {self.uname} 的直播间连接")
    
    def _register_handlers(self):
        """注册事件处理器"""
        
        @self._danmaku.on("VERIFICATION_SUCCESSFUL")
        async def on_connected(event):
            """连接成功"""
            self._connecting = False
            
            if self._is_reconnect:
                logger.info(f"[BiliLive] 已重新连接到 {self.uname} ({self.room_id})")
                # 检查是否在断线期间开播/下播
                await self._check_status_change()
            else:
                logger.info(f"[BiliLive] 已连接到 {self.uname} ({self.room_id})")
                # 初始化状态
                await self._init_live_status()
            
            self._is_reconnect = True
        
        @self._danmaku.on("LIVE")
        async def on_live(event):
            """开播事件"""
            await self._handle_live_on(event)
        
        @self._danmaku.on("PREPARING")
        async def on_preparing(event):
            """下播事件"""
            await self._handle_live_off(event)
        
        @self._danmaku.on("DANMU_MSG")
        async def on_danmu(event):
            """弹幕事件"""
            await self._handle_danmu(event)
        
        @self._danmaku.on("SEND_GIFT")
        async def on_gift(event):
            """礼物事件"""
            await self._handle_gift(event)
        
        @self._danmaku.on("SUPER_CHAT_MESSAGE")
        async def on_sc(event):
            """SC 事件"""
            await self._handle_sc(event)
        
        @self._danmaku.on("GUARD_BUY")
        async def on_guard(event):
            """大航海事件"""
            await self._handle_guard(event)
    
    async def _init_live_status(self):
        """初始化直播状态"""
        try:
            info = await self._live_room.get_room_play_info()
            status = info.get("live_status", 0)
            
            logger.info(f"[BiliLive] {self.uname} 初始直播状态: {status} (1=直播中, 0=未开播)")
            
            await self.db.set_live_status(self.room_id, status)
            
            # 同步内存标志
            self._is_live = (status == 1)
            
            if status == 1:
                start_time = info.get("live_time", int(time.time()))
                await self.db.set_live_start_time(self.room_id, start_time)
                logger.info(f"[BiliLive] {self.uname} 当前正在直播，已记录状态")
        except Exception as e:
            logger.error(f"[BiliLive] 初始化 {self.uname} 直播状态失败: {e}")
    
    async def _check_status_change(self):
        """检查断线期间的状态变化"""
        try:
            info = await self._live_room.get_room_play_info()
            now_status = info.get("live_status", 0)
            last_status = await self.db.get_live_status(self.room_id)
            
            if now_status != last_status:
                if now_status == 1:
                    logger.warning(f"[BiliLive] {self.uname} 在断线期间开播")
                    await self._handle_live_on({"data": {"live_time": info.get("live_time", 0)}})
                elif last_status == 1:
                    logger.warning(f"[BiliLive] {self.uname} 在断线期间下播")
                    await self._handle_live_off({})
        except Exception as e:
            logger.error(f"[BiliLive] 检查状态变化失败: {e}")
    
    async def _handle_live_on(self, event: Dict):
        """处理开播事件"""
        # 快速去重：使用内存标志
        if self._is_live:
            logger.debug(f"[BiliLive] {self.uname} 已在直播中（内存标志），跳过")
            return
        
        # 使用锁防止并发处理
        async with self._live_event_lock:
            # 再次检查（以防在等待锁期间事件已被处理）
            if self._is_live:
                logger.debug(f"[BiliLive] {self.uname} 已在直播中（锁内检查），跳过")
                return
            
            logger.debug(f"[BiliLive] 收到 LIVE 事件: {self.uname}")
            
            data = event.get("data", {})
            
            # 检查数据库中的状态
            current_status = await self.db.get_live_status(self.room_id)
            logger.debug(f"[BiliLive] {self.uname} 当前状态: {current_status}")
            
            if current_status == 1:
                self._is_live = True  # 同步内存标志
                logger.debug(f"[BiliLive] {self.uname} 已在直播中，跳过开播处理")
                return
            
            # 设置内存标志（在锁内，防止其他协程进入）
            self._is_live = True
        
        # 检查是否为断线重连
        now = int(time.time())
        last_end = await self.db.get_live_end_time(self.room_id)
        is_reconnect = (
            last_end != 0
            and (now - last_end) <= self.RECONNECT_THRESHOLD
            and self._last_live_push_time is not None
            and (now - self._last_live_push_time) <= self.RECONNECT_THRESHOLD
        )
        
        if is_reconnect:
            logger.info(f"[BiliLive] {self.uname} 断线重连")
            await self.db.set_live_status(self.room_id, 1)
            return
        
        logger.info(f"[BiliLive] [开播] {self.uname} ({self.room_id})")
        
        # 更新状态
        await self.db.set_live_status(self.room_id, 1)
        
        # 获取开播时间
        start_time = data.get("live_time", int(time.time()))
        if start_time == 0:
            try:
                room_info = await self._live_room.get_room_info_v2()
                live_time_str = room_info.get("live_time", "")
                if live_time_str and live_time_str != "0000-00-00 00:00:00":
                    start_time = int(datetime.strptime(live_time_str, "%Y-%m-%d %H:%M:%S").timestamp())
                else:
                    start_time = int(time.time())
            except Exception:
                start_time = int(time.time())
        
        await self.db.set_live_start_time(self.room_id, start_time)
        
        # 重置统计数据
        await self.db.reset_room_stats(self.room_id)

        # 记录最近一次开播推送时间，用于抑制极短时间内的重复 LIVE 事件
        self._last_live_push_time = now
        
        # 获取开播时的基础数据
        fans_before = -1
        fans_medal_before = -1
        guard_before = -1
        
        try:
            room_info = await self._live_room.get_room_info_v2()
            fans_before = room_info.get("attention", -1)
            
            fans_medal_info = await self._live_room.get_fans_medal_info(self.config.uid)
            fans_medal_before = fans_medal_info.get("fans_medal_light_count", -1)
            
            guards_info = await self._live_room.get_guards_info(self.config.uid)
            guard_before = guards_info.get("info", {}).get("num", -1)
        except Exception as e:
            logger.warning(f"[BiliLive] 获取 {self.uname} 基础数据失败: {e}")
        
        # 创建场次
        await self.db.create_session(
            self.room_id, start_time,
            fans_before, fans_medal_before, guard_before
        )
        
        # 调用回调
        if self._on_live_start:
            try:
                logger.info(f"[BiliLive] 准备调用开播回调: {self.uname}")
                room_info = await self._live_room.get_room_info()
                callback_data = {
                    "uname": self.uname,
                    "room_id": self.room_id,
                    "title": room_info.get("title", ""),
                    "cover": room_info.get("user_cover", ""),
                    "url": f"https://live.bilibili.com/{self.room_id}",
                }
                await self._on_live_start(self, callback_data)
                logger.info(f"[BiliLive] 开播回调执行完成: {self.uname}")
            except Exception as e:
                logger.error(f"[BiliLive] 开播回调失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.warning(f"[BiliLive] 未设置开播回调函数!")
    
    async def _handle_live_off(self, event: Dict):
        """处理下播事件"""
        # 检查是否在直播
        current_status = await self.db.get_live_status(self.room_id)
        if current_status != 1:
            return
        
        # 重置内存标志
        self._is_live = False
        
        logger.info(f"[BiliLive] [下播] {self.uname} ({self.room_id})")
        
        # 更新状态
        end_time = int(time.time())
        await self.db.set_live_status(self.room_id, 0)
        await self.db.set_live_end_time(self.room_id, end_time)
        
        # 获取下播时的基础数据
        fans_after = -1
        fans_medal_after = -1
        guard_after = -1
        
        try:
            room_info = await self._live_room.get_room_info_v2()
            fans_after = room_info.get("attention", -1)
            
            fans_medal_info = await self._live_room.get_fans_medal_info(self.config.uid)
            fans_medal_after = fans_medal_info.get("fans_medal_light_count", -1)
            
            guards_info = await self._live_room.get_guards_info(self.config.uid)
            guard_after = guards_info.get("info", {}).get("num", -1)
        except Exception as e:
            logger.warning(f"[BiliLive] 获取 {self.uname} 结束数据失败: {e}")
        
        # 结束场次
        await self.db.end_session(
            self.room_id, end_time,
            fans_after, fans_medal_after, guard_after
        )
        
        # 调用回调
        if self._on_live_end:
            try:
                await self._on_live_end(self, {
                    "uname": self.uname,
                    "room_id": self.room_id,
                })
            except Exception as e:
                logger.error(f"[BiliLive] 下播回调失败: {e}")
    
    async def _handle_danmu(self, event: Dict):
        """处理弹幕事件"""
        try:
            data = event.get("data", {})
            info = data.get("info", [])
            
            if not info or len(info) < 3:
                return
            
            uid = info[2][0] if len(info[2]) > 0 else 0
            content = info[1] if len(info) > 1 else ""
            
            # 写入缓冲
            self.db.buffer.incr_danmu(self.room_id, uid, content)
            
        except Exception as e:
            logger.debug(f"[BiliLive] 处理弹幕失败: {e}")
    
    async def _handle_gift(self, event: Dict):
        """处理礼物事件"""
        try:
            data = event.get("data", {}).get("data", {})
            
            uid = data.get("uid", 0)
            num = data.get("num", 1)
            discount_price = data.get("discount_price", 0)
            total_coin = data.get("total_coin", 0)
            gift_id = data.get("giftId", 0)
            
            # 计算收益（电池转元）
            profit = float(f"{(discount_price / 1000) * num:.1f}")
            
            # 幸运之钥特殊处理（收益为 1%）
            if gift_id == 31709:
                profit = profit * 0.01
            
            if total_coin != 0 and discount_price != 0:
                self.db.buffer.incr_gift(self.room_id, uid, profit)
            
            # 盲盒统计
            blind_gift = data.get("blind_gift")
            if blind_gift is not None:
                box_price = total_coin / 1000
                gift_num = num
                gift_price = discount_price / 1000
                box_profit = float(f"{(gift_price * gift_num) - box_price:.1f}")
                
                self.db.buffer.incr_box(self.room_id, uid, gift_num, box_profit)
            
        except Exception as e:
            logger.debug(f"[BiliLive] 处理礼物失败: {e}")
    
    async def _handle_sc(self, event: Dict):
        """处理 SC 事件"""
        try:
            data = event.get("data", {}).get("data", {})
            
            uid = data.get("uid", 0)
            price = data.get("price", 0)
            
            self.db.buffer.incr_sc(self.room_id, uid, price)
            
        except Exception as e:
            logger.debug(f"[BiliLive] 处理 SC 失败: {e}")
    
    async def _handle_guard(self, event: Dict):
        """处理大航海事件"""
        try:
            data = event.get("data", {}).get("data", {})
            
            uid = data.get("uid", 0)
            gift_name = data.get("gift_name", "")
            months = data.get("num", 1)
            
            # 映射类型
            type_map = {
                "舰长": "Captain",
                "提督": "Commander",
                "总督": "Governor",
            }
            guard_type = type_map.get(gift_name, "Captain")
            
            self.db.buffer.incr_guard(self.room_id, uid, guard_type, months)
            
        except Exception as e:
            logger.debug(f"[BiliLive] 处理大航海失败: {e}")
    
    async def generate_report_param(self) -> Dict[str, Any]:
        """
        生成直播报告参数
        
        Returns:
            直播报告所需的统计数据
        """
        # 刷新缓冲
        await self.db.buffer.flush()
        
        # 基础信息
        param = {
            "uname": self.uname,
            "room_id": self.room_id,
        }
        
        # 时间信息
        start_time = await self.db.get_live_start_time(self.room_id)
        end_time = await self.db.get_live_end_time(self.room_id)
        if end_time == 0:
            end_time = int(time.time())
        
        seconds = end_time - start_time
        minute, second = divmod(seconds, 60)
        hour, minute = divmod(minute, 60)
        
        param.update({
            "start_timestamp": start_time,
            "end_timestamp": end_time,
            "start_time": datetime.fromtimestamp(start_time).strftime("%m/%d %H:%M:%S"),
            "end_time": datetime.fromtimestamp(end_time).strftime("%m/%d %H:%M:%S"),
            "hour": hour,
            "minute": minute,
            "second": second,
        })
        
        # 房间统计
        stats = await self.db.get_room_stats(self.room_id)
        param.update({
            "danmu_count": stats["danmu_count"],
            "danmu_person_count": await self.db.get_user_count(self.room_id, "user_danmu"),
            "gift_profit": stats["gift_profit"],
            "gift_person_count": await self.db.get_user_count(self.room_id, "user_gift"),
            "sc_profit": stats["sc_profit"],
            "sc_person_count": await self.db.get_user_count(self.room_id, "user_sc"),
            "box_count": stats["box_count"],
            "box_person_count": await self.db.get_user_count(self.room_id, "user_box"),
            "box_profit": stats["box_profit"],
            "captain_count": stats["captain_count"],
            "commander_count": stats["commander_count"],
            "governor_count": stats["governor_count"],
        })
        
        # 弹幕文本（用于词云）
        param["all_danmu"] = await self.db.get_danmu_texts(self.room_id)
        
        # 时间分布数据（用于曲线图）
        param["danmu_diagram"] = await self.db.get_time_stats(self.room_id, "danmu")
        param["gift_diagram"] = await self.db.get_time_stats(self.room_id, "gift")
        param["sc_diagram"] = await self.db.get_time_stats(self.room_id, "sc")
        param["box_diagram"] = await self.db.get_time_stats(self.room_id, "box")
        param["guard_diagram"] = await self.db.get_time_stats(self.room_id, "guard")
        
        # 盲盒盈亏记录
        param["box_profit_diagram"] = await self.db.get_box_profit_records(self.room_id)
        
        return param
    
    async def get_ranking_data(self, ranking_type: str, limit: int = 10) -> Dict[str, Any]:
        """
        获取排行榜数据
        
        Args:
            ranking_type: 排行榜类型 (danmu, gift, sc, box, box_profit, captain, commander, governor)
            limit: 返回条数
            
        Returns:
            包含 uids, counts 的字典
        """
        if ranking_type == "danmu":
            data = await self.db.get_user_danmu_ranking(self.room_id, limit)
        elif ranking_type == "gift":
            data = await self.db.get_user_gift_ranking(self.room_id, limit)
        elif ranking_type == "sc":
            data = await self.db.get_user_sc_ranking(self.room_id, limit)
        elif ranking_type == "box":
            data = await self.db.get_user_box_ranking(self.room_id, limit)
        elif ranking_type == "box_profit":
            data = await self.db.get_user_box_profit_ranking(self.room_id, limit)
        elif ranking_type in ("captain", "commander", "governor"):
            data = await self.db.get_user_guard_list(self.room_id, ranking_type.capitalize())
        else:
            return {"uids": [], "counts": []}
        
        return {
            "uids": [item[0] for item in data],
            "counts": [item[1] for item in data],
        }
