"""
Bilibili Live Room API
Ported from StarBot's live.py with simplifications
"""

import json
from typing import Dict, Any, Optional

from ..utils.network import request
from ..utils.credential import credential_manager


# API endpoints from StarBot
API = {
    "room_play_info": {
        "url": "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo",
        "method": "GET",
    },
    "room_info": {
        "url": "https://api.live.bilibili.com/room/v1/Room/get_info",
        "method": "GET",
    },
    "room_info_v2": {
        "url": "https://api.live.bilibili.com/xlive/web-room/v1/index/getH5InfoByRoom",
        "method": "GET",
    },
    "user_info": {
        "url": "https://api.live.bilibili.com/live_user/v1/Master/info",
        "method": "GET",
    },
    "fans_medal_info": {
        "url": "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/fans",
        "method": "GET",
    },
    "guards_info": {
        "url": "https://api.live.bilibili.com/xlive/app-room/v2/guardTab/topList",
        "method": "GET",
    },
    "chat_conf": {
        "url": "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo",
        "method": "GET",
    },
}


class LiveRoom:
    """
    直播间类，用于获取直播间各种信息
    """
    
    def __init__(self, room_id: int):
        """
        Args:
            room_id: 房间号（支持短号，会自动转换为真实房间号）
        """
        self.room_display_id = room_id
        self.room_id: Optional[int] = None
        self.uid: Optional[int] = None
    
    async def get_room_play_info(self) -> Dict[str, Any]:
        """
        获取房间信息（真实房间号，直播状态等）
        """
        api = API["room_play_info"]
        params = {"room_id": self.room_display_id}
        data = await request(api["method"], api["url"], params=params, credential=credential_manager)
        
        # 缓存真实房间号和主播 UID
        self.room_id = data.get("room_id", self.room_display_id)
        self.uid = data.get("uid")
        
        return data
    
    async def get_real_room_id(self) -> int:
        """获取真实房间号"""
        if self.room_id is None:
            await self.get_room_play_info()
        return self.room_id
    
    async def get_room_info(self) -> Dict[str, Any]:
        """
        获取直播间信息（标题，简介等）
        """
        api = API["room_info"]
        params = {"room_id": await self.get_real_room_id()}
        return await request(api["method"], api["url"], params=params, credential=credential_manager)
    
    async def get_room_info_v2(self) -> Dict[str, Any]:
        """
        获取直播间信息 V2（更详细）
        """
        api = API["room_info_v2"]
        params = {"room_id": await self.get_real_room_id()}
        data = await request(api["method"], api["url"], params=params, credential=credential_manager)
        return data.get("room_info", {})
    
    async def get_user_info(self, uid: int) -> Dict[str, Any]:
        """
        获取主播信息
        
        Args:
            uid: 主播 UID
        """
        api = API["user_info"]
        params = {"uid": uid}
        return await request(api["method"], api["url"], params=params, credential=credential_manager)
    
    async def get_fans_medal_info(self, uid: int) -> Dict[str, Any]:
        """
        获取粉丝勋章信息
        
        Args:
            uid: 主播 UID
        """
        api = API["fans_medal_info"]
        params = {
            "target_id": uid,
            "page_size": 1
        }
        return await request(api["method"], api["url"], params=params, credential=credential_manager)
    
    async def get_guards_info(self, uid: int) -> Dict[str, Any]:
        """
        获取大航海信息
        
        Args:
            uid: 主播 UID
        """
        api = API["guards_info"]
        room_id = await self.get_real_room_id()
        params = {
            "roomid": room_id,
            "ruid": uid,
            "page": 1,
            "page_size": 1
        }
        return await request(api["method"], api["url"], params=params, credential=credential_manager)
    
    async def get_chat_conf(self) -> Dict[str, Any]:
        """
        获取弹幕服务器配置信息
        """
        api = API["chat_conf"]
        params = {
            "id": await self.get_real_room_id(),
            "type": 0
        }
        return await request(api["method"], api["url"], params=params, credential=credential_manager)
