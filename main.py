"""
AstrBot Bilibili Live Plugin - 直播全功能插件
"""

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

try:
    from astrbot.api.star import StarTools
    HAS_STAR_TOOLS = True
except ImportError:
    HAS_STAR_TOOLS = False

from .core.models import LiveOff, LiveOn, LiveReport, PushTarget, PushType, RoomConfig
from .core.room_monitor import RoomMonitor
from .painter.live_report import LiveReportGenerator
from .storage.stats_db import StatsDB
from .utils.credential import set_credential

PLUGIN_NAME = "bilive_all"


@register(
    PLUGIN_NAME,
    "GEMILUXVII",
    "B站直播全功能插件 - 开播/下播提醒、直播数据统计报告",
    "1.0.3",
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
        self.db: StatsDB | None = None

        # 房间监控器
        self.monitors: dict[int, RoomMonitor] = {}

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
            sessdata = self.config.get("sessdata", "") if self.config else ""
            bili_jct = self.config.get("bili_jct", "") if self.config else ""
            buvid3 = self.config.get("buvid3", "") if self.config else ""

            if sessdata and bili_jct:
                set_credential(sessdata, bili_jct, buvid3)
                buvid_status = f"buvid3: {buvid3[:8]}..." if buvid3 else "buvid3: 未配置!"
                logger.info(f"[BiliLive] 已加载 B站凭据 (SESSDATA: {sessdata[:10]}..., {buvid_status})")
                if not buvid3:
                    logger.warning("[BiliLive] 警告: buvid3 未配置，WebSocket连接可能失败!")
            else:
                logger.warning("[BiliLive] 未配置 B站凭据，部分功能可能受限")

            # 加载已保存的房间配置（从配置文件）
            await self._load_rooms()

            # 加载持久化存储的房间订阅
            await self._load_saved_rooms()

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

    async def _add_monitor(self, config: RoomConfig, save_to_db: bool = False):
        """添加房间监控

        Args:
            config: 房间配置
            save_to_db: 是否保存到数据库（手动添加时为 True）
        """
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
            # 更新 config 中的房间信息
            config.room_id = monitor.room_id
            config.uname = monitor.uname
            # 保存到数据库
            if save_to_db:
                await self._save_room_config(config)
            return True
        return False

    async def _remove_monitor(self, uid: int, delete_from_db: bool = False):
        """移除房间监控

        Args:
            uid: 主播 UID
            delete_from_db: 是否从数据库删除（手动删除时为 True）
        """
        if uid not in self.monitors:
            return False

        monitor = self.monitors.pop(uid)
        await monitor.disconnect()

        # 从数据库删除
        if delete_from_db:
            await self._delete_room_config(uid)
        return True

    def _build_session_id(self, target: PushTarget) -> str:
        """构建 AstrBot 格式的会话 ID"""
        # 使用 'default' 作为平台 ID（这是 aiocqhttp 适配器的默认 ID）
        if target.type == PushType.Group:
            return f"default:GroupMessage:{target.id}"
        else:
            return f"default:FriendMessage:{target.id}"

    async def _save_room_config(self, config: RoomConfig):
        """保存房间配置到数据库"""
        if not self.db:
            return
        try:
            import json
            targets_json = json.dumps([{
                "id": t.id,
                "type": t.type.value,
                "live_on": t.live_on.enabled,
                "live_off": t.live_off.enabled,
                "live_report": t.live_report.enabled,
            } for t in config.targets])

            await self.db._conn.execute("""
                INSERT OR REPLACE INTO room_subscriptions (uid, room_id, uname, targets)
                VALUES (?, ?, ?, ?)
            """, (config.uid, config.room_id, config.uname, targets_json))
            await self.db._conn.commit()
            logger.info(f"[BiliLive] 已保存房间配置: {config.uname} (UID: {config.uid})")
        except Exception as e:
            logger.error(f"[BiliLive] 保存房间配置失败: {e}")

    async def _delete_room_config(self, uid: int):
        """从数据库删除房间配置"""
        if not self.db:
            return
        try:
            await self.db._conn.execute("DELETE FROM room_subscriptions WHERE uid = ?", (uid,))
            await self.db._conn.commit()
            logger.info(f"[BiliLive] 已删除房间配置: UID {uid}")
        except Exception as e:
            logger.error(f"[BiliLive] 删除房间配置失败: {e}")

    async def _load_saved_rooms(self):
        """从数据库加载保存的房间配置"""
        if not self.db:
            return
        try:
            import json
            async with self.db._conn.execute("SELECT uid, room_id, uname, targets FROM room_subscriptions") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    uid, room_id, uname, targets_json = row
                    targets_data = json.loads(targets_json) if targets_json else []

                    targets = []
                    for t in targets_data:
                        targets.append(PushTarget(
                            id=t["id"],
                            type=PushType.Group if t.get("type", 1) == 1 else PushType.Friend,
                            live_on=LiveOn(enabled=t.get("live_on", True)),
                            live_off=LiveOff(enabled=t.get("live_off", True)),
                            live_report=LiveReport(enabled=t.get("live_report", True)),
                        ))

                    config = RoomConfig(uid=uid, room_id=room_id, uname=uname, targets=targets)
                    logger.info(f"[BiliLive] 加载保存的房间: {uname} (UID: {uid})")
                    await self._add_monitor(config)
        except Exception as e:
            logger.error(f"[BiliLive] 加载保存的房间失败: {e}")

    async def _on_live_start(self, monitor: RoomMonitor, data: dict):
        """开播事件回调"""
        logger.info(f"[BiliLive] 触发开播推送: {data.get('uname')}")

        for target in monitor.config.get_enabled_targets("live_on"):
            try:
                # 构建消息（不包含封面，封面单独处理）
                uname = data.get("uname", "")
                title = data.get("title", "")
                url = data.get("url", "")
                cover_url = data.get("cover", "")

                # 消息模板处理（移除 {cover} 占位符，因为要用 Image 组件发送）
                message_template = target.live_on.message
                # 如果模板包含 {cover}，移除它（我们会单独发送图片）
                message_template = message_template.replace("{cover}", "")

                message = message_template.format(
                    uname=uname,
                    title=title,
                    url=url,
                )

                # 构建会话 ID
                session_id = self._build_session_id(target)

                result = MessageEventResult()
                result.chain.append(Plain(message.strip()))

                # 如果有封面，添加 Image 组件
                if cover_url:
                    result.chain.append(Image.fromURL(cover_url))

                await self.context.send_message(session_id, result)
                logger.info(f"[BiliLive] 开播推送成功: {session_id}")

            except Exception as e:
                logger.error(f"[BiliLive] 开播推送失败: {e}")

    async def _on_live_end(self, monitor: RoomMonitor, data: dict):
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

                session_id = self._build_session_id(target)

                result = MessageEventResult()
                result.chain.append(Plain(message))
                await self.context.send_message(session_id, result)

            except Exception as e:
                logger.error(f"[BiliLive] 下播推送失败: {e}")

        # 发送直播报告
        for target in monitor.config.get_enabled_targets("live_report"):
            try:
                report_b64 = LiveReportGenerator.generate(report_param, target.live_report)

                session_id = self._build_session_id(target)

                result = MessageEventResult()
                result.chain.append(Image.fromBase64(report_b64))
                await self.context.send_message(session_id, result)

            except Exception as e:
                logger.error(f"[BiliLive] 报告推送失败: {e}")

    def _get_help(self) -> str:
        """获取帮助信息"""
        return """📺 B站直播监控插件

命令：
/bilive_add <UID> - 添加主播监控
/bilive_rm <UID> - 移除主播监控
/bilive_list - 列出监控中的主播
/bilive_status - 查看插件状态
/bilive_help - 显示此帮助"""

    @filter.command("bilive_add")
    async def cmd_add(self, event: AstrMessageEvent, uid: str = None):
        """
        添加主播监控

        用法: /bilive_add <UID>
        示例: /bilive_add 403039446
        """
        if uid is None:
            yield event.plain_result("请指定主播 UID\n用法: /bilive_add <UID>\n示例: /bilive_add 403039446")
            return

        try:
            uid_int = int(uid)
        except ValueError:
            yield event.plain_result("❌ UID 必须是数字")
            return

        if uid_int in self.monitors:
            yield event.plain_result(f"⚠️ UID {uid_int} 已在监控中")
            return

        # 获取发送者信息作为推送目标
        sender_id = event.get_sender_id()
        group_id = event.get_group_id()

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

        config = RoomConfig(uid=uid_int, targets=targets)

        yield event.plain_result(f"⏳ 正在添加监控 UID {uid_int}...")

        success = await self._add_monitor(config, save_to_db=True)

        if success:
            monitor = self.monitors.get(uid_int)
            yield event.plain_result(f"✅ 已添加监控: {monitor.uname} (UID: {uid_int}, 房间号: {monitor.room_id})")
        else:
            yield event.plain_result(f"❌ 添加监控失败: UID {uid_int}")

    @filter.command("bilive_rm")
    async def cmd_remove(self, event: AstrMessageEvent, uid: str = None):
        """
        移除主播监控

        用法: /bilive_rm <UID>
        示例: /bilive_rm 403039446
        """
        if uid is None:
            yield event.plain_result("请指定主播 UID\n用法: /bilive_rm <UID>")
            return

        try:
            uid_int = int(uid)
        except ValueError:
            yield event.plain_result("❌ UID 必须是数字")
            return

        if uid_int not in self.monitors:
            yield event.plain_result(f"⚠️ UID {uid_int} 不在监控中")
            return

        monitor = self.monitors.get(uid_int)
        uname = monitor.uname if monitor else uid_int

        success = await self._remove_monitor(uid_int, delete_from_db=True)
        if success:
            yield event.plain_result(f"✅ 已移除监控: {uname} (UID: {uid_int})")
        else:
            yield event.plain_result(f"❌ 移除监控失败: UID {uid_int}")

    @filter.command("bilive_list")
    async def cmd_list(self, event: AstrMessageEvent):
        """
        列出监控中的主播

        用法: /bilive_list
        """
        if not self.monitors:
            yield event.plain_result("📺 当前没有监控任何主播")
            return

        lines = ["📺 监控列表:"]
        for uid, monitor in self.monitors.items():
            status = "🟢 连接中" if monitor.status == 2 else "🔴 断开"
            lines.append(f"  • {monitor.uname} (UID: {uid}) {status}")

        yield event.plain_result("\n".join(lines))

    @filter.command("bilive_status")
    async def cmd_status(self, event: AstrMessageEvent):
        """
        查看插件状态

        用法: /bilive_status
        """
        lines = ["📊 BiliLive 插件状态:"]
        lines.append(f"  • 监控数量: {len(self.monitors)}")
        lines.append(f"  • 数据库: {'✅ 已连接' if self.db else '❌ 未连接'}")

        connected = sum(1 for m in self.monitors.values() if m.status == 2)
        lines.append(f"  • 连接数: {connected}/{len(self.monitors)}")

        yield event.plain_result("\n".join(lines))

    @filter.command("bilive_help")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        yield event.plain_result(self._get_help())

    async def terminate(self):
        """插件终止"""
        logger.info("[BiliLive] 正在关闭插件...")

        # 断开所有监控
        for uid in list(self.monitors.keys()):
            await self._remove_monitor(uid)

        # 关闭数据库
        if self.db:
            await self.db.close()

        # 关闭网络 session
        from .utils.network import close_session
        await close_session()

        logger.info("[BiliLive] 插件已关闭")

