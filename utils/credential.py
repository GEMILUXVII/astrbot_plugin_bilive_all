"""
Bilibili credential management
"""

from typing import Dict, Optional
from ..core.models import Credential


class CredentialManager:
    """B站凭据管理器"""
    
    _instance: Optional["CredentialManager"] = None
    _credential: Optional[Credential] = None
    _uid_cache: Optional[int] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "CredentialManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_credential(self, credential: Credential):
        """设置凭据"""
        self._credential = credential
        self._uid_cache = None
    
    def set_credential_from_config(self, sessdata: str, bili_jct: str, buvid3: str = ""):
        """从配置设置凭据"""
        self._credential = Credential(
            sessdata=sessdata,
            bili_jct=bili_jct,
            buvid3=buvid3
        )
        self._uid_cache = None
    
    def get_credential(self) -> Optional[Credential]:
        """获取凭据"""
        return self._credential
    
    def get_cookies(self) -> Dict[str, str]:
        """获取用于请求的 cookies"""
        if self._credential is None:
            return {}
        
        cookies = {}
        if self._credential.sessdata:
            cookies["SESSDATA"] = self._credential.sessdata
        if self._credential.bili_jct:
            cookies["bili_jct"] = self._credential.bili_jct
        if self._credential.buvid3:
            cookies["buvid3"] = self._credential.buvid3
        
        return cookies
    
    def is_valid(self) -> bool:
        """检查凭据是否有效"""
        return self._credential is not None and self._credential.is_valid()

    async def get_uid(self) -> int:
        """获取当前账号 UID，用于 WebSocket 认证"""
        if self._uid_cache is not None:
            return self._uid_cache

        if not self.is_valid():
            self._uid_cache = 0
            return 0

        # 延迟导入以避免循环依赖
        from .network import request

        try:
            result = await request(
                "GET",
                "https://api.bilibili.com/x/web-interface/nav",
                credential=credential_manager,
            )
            self._uid_cache = int(result.get("mid", 0) or 0)
        except Exception:
            self._uid_cache = 0
        return self._uid_cache


# 全局凭据管理器
credential_manager = CredentialManager.get_instance()


def set_credential(sessdata: str, bili_jct: str, buvid3: str = ""):
    """设置全局凭据"""
    credential_manager.set_credential_from_config(sessdata, bili_jct, buvid3)


def get_credential() -> Optional[Credential]:
    """获取全局凭据"""
    return credential_manager.get_credential()
