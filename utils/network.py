"""
Network utilities for Bilibili API requests
Ported from StarBot with simplifications
"""

import aiohttp
from typing import Dict, Any, Optional

from .credential import CredentialManager


_session: Optional[aiohttp.ClientSession] = None


async def get_session() -> aiohttp.ClientSession:
    """获取或创建 aiohttp session"""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close_session():
    """关闭 aiohttp session"""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def request(
    method: str,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    credential: Optional[CredentialManager] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    发送 HTTP 请求到 Bilibili API
    
    Args:
        method: HTTP 方法 (GET, POST)
        url: 请求 URL
        params: URL 参数
        data: POST 数据
        credential: 凭据管理器
        
    Returns:
        API 返回的 data 字段
    """
    session = await get_session()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://live.bilibili.com/",
    }
    
    cookies = {}
    if credential:
        cookies = credential.get_cookies()
    
    async with session.request(
        method=method,
        url=url,
        params=params,
        data=data,
        headers=headers,
        cookies=cookies,
        **kwargs
    ) as resp:
        resp.raise_for_status()
        result = await resp.json()
        
        if result.get("code") != 0:
            raise APIException(result.get("code", -1), result.get("message", "Unknown error"))
        
        return result.get("data", {})


async def download_image(url: str) -> bytes:
    """下载图片"""
    session = await get_session()
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.read()


class APIException(Exception):
    """Bilibili API 异常"""
    
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"API Error {code}: {message}")
