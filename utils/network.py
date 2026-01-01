"""
Network utilities for Bilibili API requests
Ported from StarBot with simplifications
"""

import asyncio
import aiohttp
import random
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
    max_retries: int = 5,
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
        max_retries: 最大重试次数
        
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
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
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
                
                code = result.get("code", 0)
                
                # 频率限制错误，需要退避重试
                if code == -799:
                    last_exception = APIException(code, result.get("message", "请求过于频繁"))
                    base = min((attempt + 1) * 2, 15)
                    jitter = random.uniform(0.8, 1.4)
                    wait_time = base * jitter
                    await asyncio.sleep(wait_time)
                    continue
                
                if code != 0:
                    raise APIException(code, result.get("message", "Unknown error"))
                
                return result.get("data", {})
                
        except aiohttp.ClientError as e:
            last_exception = e
            await asyncio.sleep(1 + random.uniform(0, 0.5))
            continue
    
    # 所有重试都失败
    if last_exception:
        raise last_exception
    raise APIException(-1, "请求失败")


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
