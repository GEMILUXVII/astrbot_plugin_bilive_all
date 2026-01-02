"""
Pydantic configuration models for BiliLive plugin
Ported from StarBot with modifications for AstrBot
"""

from enum import Enum

from pydantic import BaseModel


class PushType(Enum):
    """
    推送目标类型
    + Friend : 0 - 私聊推送
    + Group  : 1 - 群聊推送
    """
    Friend = 0
    Group = 1


class LiveOn(BaseModel):
    """开播推送配置"""

    enabled: bool = False
    """是否启用开播推送"""

    message: str = "{uname} 正在直播 {title}\n{url}\n{cover}"
    """
    开播推送内容模板
    占位符：{uname} 主播昵称，{title} 直播间标题，{url} 直播间链接，{cover} 封面图
    """

    @classmethod
    def default(cls) -> "LiveOn":
        return LiveOn(enabled=True)


class LiveOff(BaseModel):
    """下播推送配置"""

    enabled: bool = False
    """是否启用下播推送"""

    message: str = "{uname} 直播结束了"
    """下播推送内容模板，占位符：{uname} 主播昵称"""

    @classmethod
    def default(cls) -> "LiveOff":
        return LiveOff(enabled=True)


class LiveReport(BaseModel):
    """
    直播报告配置
    直播报告会在下播推送后发出
    """

    enabled: bool = False
    """是否启用直播报告"""

    logo: str | None = None
    """主播立绘的路径，会绘制在直播报告右上角"""

    logo_base64: str | None = None
    """主播立绘的 Base64 字符串"""

    # 基础数据展示选项
    time: bool = True
    """是否展示直播时间段和时长"""

    fans_change: bool = True
    """是否展示粉丝变动"""

    fans_medal_change: bool = True
    """是否展示粉丝团变动"""

    guard_change: bool = True
    """是否展示大航海变动"""

    # 直播数据展示选项
    danmu: bool = True
    """是否展示弹幕数、发送人数"""

    box: bool = True
    """是否展示盲盒数、盲盒盈亏"""

    gift: bool = True
    """是否展示礼物收益、送礼人数"""

    sc: bool = True
    """是否展示SC收益、发送人数"""

    guard: bool = True
    """是否展示大航海开通数"""

    # 排行榜配置 (0 = 不展示)
    danmu_ranking: int = 3
    """弹幕排行榜前N名"""

    box_ranking: int = 3
    """盲盒数量排行榜前N名"""

    box_profit_ranking: int = 3
    """盲盒盈亏排行榜前N名"""

    gift_ranking: int = 3
    """礼物排行榜前N名"""

    sc_ranking: int = 3
    """SC排行榜前N名"""

    guard_list: bool = True
    """是否展示大航海观众列表"""

    # 曲线图配置
    box_profit_diagram: bool = True
    """是否展示盲盒盈亏曲线图"""

    danmu_diagram: bool = True
    """是否展示弹幕互动曲线图"""

    box_diagram: bool = True
    """是否展示盲盒互动曲线图"""

    gift_diagram: bool = True
    """是否展示礼物互动曲线图"""

    sc_diagram: bool = True
    """是否展示SC互动曲线图"""

    guard_diagram: bool = True
    """是否展示大航海互动曲线图"""

    danmu_cloud: bool = True
    """是否生成弹幕词云"""

    @classmethod
    def default(cls) -> "LiveReport":
        """获取功能全部开启的默认配置"""
        return LiveReport(enabled=True)

    @classmethod
    def minimal(cls) -> "LiveReport":
        """获取精简版配置（只有基础统计，无图表）"""
        return LiveReport(
            enabled=True,
            box_profit_diagram=False,
            danmu_diagram=False,
            box_diagram=False,
            gift_diagram=False,
            sc_diagram=False,
            guard_diagram=False,
            danmu_cloud=False,
        )


class PushTarget(BaseModel):
    """推送目标配置"""

    id: int
    """QQ 号或群号"""

    type: PushType = PushType.Group
    """推送类型"""

    live_on: LiveOn = LiveOn()
    """开播推送配置"""

    live_off: LiveOff = LiveOff()
    """下播推送配置"""

    live_report: LiveReport = LiveReport()
    """直播报告配置"""


class RoomConfig(BaseModel):
    """房间监控配置"""

    uid: int
    """主播 UID"""

    room_id: int | None = None
    """直播间房间号（可自动获取）"""

    uname: str | None = None
    """主播昵称（可自动获取）"""

    targets: list[PushTarget] = []
    """推送目标列表"""

    def get_enabled_targets(self, feature: str) -> list[PushTarget]:
        """获取启用了指定功能的推送目标"""
        result = []
        for target in self.targets:
            if feature == "live_on" and target.live_on.enabled:
                result.append(target)
            elif feature == "live_off" and target.live_off.enabled:
                result.append(target)
            elif feature == "live_report" and target.live_report.enabled:
                result.append(target)
        return result


class Credential(BaseModel):
    """B站账号凭据"""

    sessdata: str = ""
    """B站账号的 sessdata"""

    bili_jct: str = ""
    """B站账号的 bili_jct"""

    buvid3: str = ""
    """B站账号的 buvid3"""

    def is_valid(self) -> bool:
        """检查凭据是否有效"""
        return bool(self.sessdata and self.bili_jct)
