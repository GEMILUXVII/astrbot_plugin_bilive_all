"""
AstrBot Bilibili Live Plugin - 直播全功能插件
"""

import asyncio
from pathlib import Path
from typing import Dict, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import command, event_message_type, EventMessageType
from astrbot.api.message_components import Plain, Image
from astrbot.api.star import Context, Star, register

try:
    from astrbot.api.star import StarTools
    HAS_STAR_TOOLS = True
except ImportError:
    HAS_STAR_TOOLS = False

from .core.models import RoomConfig, PushTarget, PushType, LiveOn, LiveOff, LiveReport
from .core.room_monitor import RoomMonitor
from .storage.stats_db import StatsDB
from .painter.live_report import LiveReportGenerator
from .utils.credential import set_credential


PLUGIN_NAME = "bilive_all"


@register(
    PLUGIN_NAME,
    "GEMILUXVII",
    "B站直播全功能插件 - 开播/下播提醒、直播数据统计报告",
    "1.0.0",
    "https://github.com/GEMILUXVII/astrbot_plugin_bilive_all",
)
class BiliLivePlugin(Star):
    """
    B站直播监控插件
    
    功能：
    - 监控多个直播间
    - 开播/下播通知
    - 直播数据统计报告
    - 弹幕词云
    """
    
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.context = context
        self.config = config or {}
        
        # 数据目录
        try:
            if HAS_STAR_TOOLS:
                self.data_dir = StarTools.get_data_dir(PLUGIN_NAME)
            else:
                # 回退到插件目录
                self.data_dir = Path(__file__).parent / "data"
        except Exception:
            self.data_dir = Path(__file__).parent / "data"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 统计数据库
        self.db: Optional[StatsDB] = None
        
        # 房间监控器
        self.monitors: Dict[int, RoomMonitor] = {}
        
        # 启动初始化
        asyncio.create_task(self._init_plugin())
    
    async def _init_plugin(self):
        """初始化插件"""
        try:
            # 初始化数据库
            db_path = self.data_dir / "stats.db"
            self.db = StatsDB(db_path)
            await self.db.init()
            
            # 设置凭据
            sessdata = self.config.get("sessdata", "")
            bili_jct = self.config.get("bili_jct", "")
            buvid3 = self.config.get("buvid3", "")
            if sessdata and bili_jct:
                set_credential(sessdata, bili_jct, buvid3)
            
            # 加载已保存的房间配置
            await self._load_rooms()
            
            logger.info("[BiliLive] 插件初始化完成")
            
        except Exception as e:
            logger.error(f"[BiliLive] 插件初始化失败: {e}")
    
    async def _load_rooms(self):
        """加载房间配置"""
        rooms_config = self.config.get("rooms", [])
        
        for room_cfg in rooms_config:
            try:
                uid = room_cfg.get("uid")
                if not uid:
                    continue
                
                # 构建推送目标
                targets = []
                for target_cfg in room_cfg.get("targets", []):
                    target = PushTarget(
                        id=target_cfg.get("id"),
                        type=PushType.Group if target_cfg.get("type") == "group" else PushType.Friend,
                        live_on=LiveOn(enabled=target_cfg.get("live_on", True)),
                        live_off=LiveOff(enabled=target_cfg.get("live_off", True)),
                        live_report=LiveReport(enabled=target_cfg.get("live_report", True)),
                    )
                    targets.append(target)
                
                config = RoomConfig(
                    uid=uid,
                    room_id=room_cfg.get("room_id"),
                    uname=room_cfg.get("uname"),
                    targets=targets,
                )
                
                await self._add_monitor(config)
                
            except Exception as e:
                logger.error(f"[BiliLive] 加载房间配置失败: {e}")
    
    async def _add_monitor(self, config: RoomConfig):
        """添加房间监控"""
        if config.uid in self.monitors:
            logger.warning(f"[BiliLive] 房间 {config.uid} 已在监控中")
            return False
        
        monitor = RoomMonitor(
            config=config,
            db=self.db,
            on_live_start=self._on_live_start,
            on_live_end=self._on_live_end,
        )
        
        success = await monitor.connect()
        if success:
            self.monitors[config.uid] = monitor
            return True
        return False
    
    async def _remove_monitor(self, uid: int):
        """移除房间监控"""
        if uid not in self.monitors:
            return False
        
        monitor = self.monitors.pop(uid)
        await monitor.disconnect()
        return True
    
    async def _on_live_start(self, monitor: RoomMonitor, data: Dict):
        """开播事件回调"""
        logger.info(f"[BiliLive] 触发开播推送: {data.get('uname')}")
        
        for target in monitor.config.get_enabled_targets("live_on"):
            try:
                # 构建消息
                message = target.live_on.message.format(
                    uname=data.get("uname", ""),
                    title=data.get("title", ""),
                    url=data.get("url", ""),
                    cover=f"[CQ:image,file={data.get('cover', '')}]" if data.get("cover") else "",
                )
                
                # 发送消息
                result = MessageEventResult()
                result.chain = [Plain(message)]
                
                await self.context.send_message(
                    target_id=str(target.id),
                    platform="qq",  # 根据实际平台调整
                    message_chain=result,
                )
                
            except Exception as e:
                logger.error(f"[BiliLive] 开播推送失败: {e}")
    
    async def _on_live_end(self, monitor: RoomMonitor, data: Dict):
        """下播事件回调"""
        logger.info(f"[BiliLive] 触发下播推送: {data.get('uname')}")
        
        # 生成报告参数
        report_param = await monitor.generate_report_param()
        
        for target in monitor.config.get_enabled_targets("live_off"):
            try:
                # 下播消息
                message = target.live_off.message.format(
                    uname=data.get("uname", ""),
                )
                
                result = MessageEventResult()
                result.chain = [Plain(message)]
                
                await self.context.send_message(
                    target_id=str(target.id),
                    platform="qq",
                    message_chain=result,
                )
                
            except Exception as e:
                logger.error(f"[BiliLive] 下播推送失败: {e}")
        
        # 发送直播报告
        for target in monitor.config.get_enabled_targets("live_report"):
            try:
                report_b64 = LiveReportGenerator.generate(report_param, target.live_report)
                
                result = MessageEventResult()
                result.chain = [Image.fromBase64(report_b64)]
                
                await self.context.send_message(
                    target_id=str(target.id),
                    platform="qq",
                    message_chain=result,
                )
                
            except Exception as e:
                logger.error(f"[BiliLive] 报告推送失败: {e}")
    
    @command("bilive")
    async def bilive_cmd(self, event: AstrMessageEvent, action: str = None, *args):
        """
        /bilive <action> [args...]
        
        Actions:
        - add <uid> - 添加监控
        - remove <uid> - 移除监控
        - list - 列出监控
        - status - 查看状态
        """
        if action is None:
            yield event.plain_result(self._get_help())
            return
        
        action = action.lower()
        
        if action == "add":
            yield event.plain_result(await self._cmd_add(event, args))
        elif action == "remove":
            yield event.plain_result(await self._cmd_remove(args))
        elif action == "list":
            yield event.plain_result(self._cmd_list())
        elif action == "status":
            yield event.plain_result(self._cmd_status())
        else:
            yield event.plain_result(f"未知操作: {action}\n\n{self._get_help()}")
    
    def _get_help(self) -> str:
        """获取帮助信息"""
        return """B站直播监控插件

命令：
/bilive add <uid> - 添加主播监控
/bilive remove <uid> - 移除主播监控
/bilive list - 列出监控中的主播
/bilive status - 查看插件状态"""
    
    async def _cmd_add(self, event: AstrMessageEvent, args) -> str:
        """添加监控"""
        if not args:
            return "请指定主播 UID\n用法: /bilive add <uid>"
        
        try:
            uid = int(args[0])
        except ValueError:
            return "UID 必须是数字"
        
        if uid in self.monitors:
            return f"UID {uid} 已在监控中"
        
        # 获取发送者信息作为推送目标
        sender_id = event.get_sender_id()
        group_id = event.message_obj.group_id if hasattr(event.message_obj, 'group_id') else None
        
        targets = []
        if group_id:
            targets.append(PushTarget(
                id=int(group_id),
                type=PushType.Group,
                live_on=LiveOn.default(),
                live_off=LiveOff.default(),
                live_report=LiveReport.default(),
            ))
        elif sender_id:
            targets.append(PushTarget(
                id=int(sender_id),
                type=PushType.Friend,
                live_on=LiveOn.default(),
                live_off=LiveOff.default(),
                live_report=LiveReport.default(),
            ))
        
        config = RoomConfig(uid=uid, targets=targets)
        success = await self._add_monitor(config)
        
        if success:
            monitor = self.monitors.get(uid)
            return f"✅ 已添加监控: {monitor.uname} (UID: {uid}, 房间号: {monitor.room_id})"
        else:
            return f"❌ 添加监控失败: UID {uid}"
    
    async def _cmd_remove(self, args) -> str:
        """移除监控"""
        if not args:
            return "请指定主播 UID\n用法: /bilive remove <uid>"
        
        try:
            uid = int(args[0])
        except ValueError:
            return "UID 必须是数字"
        
        if uid not in self.monitors:
            return f"UID {uid} 不在监控中"
        
        monitor = self.monitors.get(uid)
        uname = monitor.uname if monitor else uid
        
        success = await self._remove_monitor(uid)
        if success:
            return f"✅ 已移除监控: {uname} (UID: {uid})"
        else:
            return f"❌ 移除监控失败: UID {uid}"
    
    def _cmd_list(self) -> str:
        """列出监控"""
        if not self.monitors:
            return "📺 当前没有监控任何主播"
        
        lines = ["📺 监控列表:"]
        for uid, monitor in self.monitors.items():
            status = "🟢 连接中" if monitor.status == 2 else "🔴 断开"
            lines.append(f"  • {monitor.uname} (UID: {uid}) {status}")
        
        return "\n".join(lines)
    
    def _cmd_status(self) -> str:
        """查看状态"""
        lines = ["📊 BiliLive 插件状态:"]
        lines.append(f"  • 监控数量: {len(self.monitors)}")
        lines.append(f"  • 数据库: {'✅ 已连接' if self.db else '❌ 未连接'}")
        
        connected = sum(1 for m in self.monitors.values() if m.status == 2)
        lines.append(f"  • 连接数: {connected}/{len(self.monitors)}")
        
        return "\n".join(lines)
    
    async def terminate(self):
        """插件终止"""
        logger.info("[BiliLive] 正在关闭插件...")
        
        # 断开所有监控
        for uid in list(self.monitors.keys()):
            await self._remove_monitor(uid)
        
        # 关闭数据库
        if self.db:
            await self.db.close()
        
        logger.info("[BiliLive] 插件已关闭")
