"""
WBI 签名工具
用于 Bilibili API 的 wbi 签名验证
参考: https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/sign/wbi.html
"""

from functools import reduce
from hashlib import md5
import urllib.parse
import time
from typing import Dict, Tuple, Optional

from .credential import credential_manager


# wbi 混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

# 缓存 wbi keys
_wbi_keys_cache: Optional[Tuple[str, str, float]] = None
WBI_KEYS_CACHE_TTL = 3600  # 1小时缓存


def _get_mixin_key(orig: str) -> str:
    """获取混淆后的 key"""
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]


def enc_wbi(params: Dict, img_key: str, sub_key: str) -> Dict:
    """
    对参数进行 wbi 签名
    
    Args:
        params: 原始参数
        img_key: img_key
        sub_key: sub_key
        
    Returns:
        签名后的参数
    """
    mixin_key = _get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time
    params = dict(sorted(params.items()))
    # 过滤特殊字符
    params = {
        k: ''.join(filter(lambda c: c not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params['w_rid'] = wbi_sign
    return params


async def get_wbi_keys() -> Tuple[str, str]:
    """
    获取最新的 img_key 和 sub_key
    
    Returns:
        (img_key, sub_key) 元组
    """
    global _wbi_keys_cache
    
    # 检查缓存
    if _wbi_keys_cache:
        img_key, sub_key, cached_time = _wbi_keys_cache
        if time.time() - cached_time < WBI_KEYS_CACHE_TTL:
            return img_key, sub_key
    
    # 需要动态导入避免循环依赖
    from .network import request
    
    result = await request(
        "GET",
        "https://api.bilibili.com/x/web-interface/nav",
        credential=credential_manager
    )
    
    img_url = result.get('wbi_img', {}).get('img_url', '')
    sub_url = result.get('wbi_img', {}).get('sub_url', '')
    
    img_key = img_url.rsplit('/', 1)[-1].split('.')[0] if img_url else ''
    sub_key = sub_url.rsplit('/', 1)[-1].split('.')[0] if sub_url else ''
    
    # 缓存结果
    _wbi_keys_cache = (img_key, sub_key, time.time())
    
    return img_key, sub_key


async def sign_params(params: Dict) -> Dict:
    """
    对参数进行 wbi 签名（自动获取 keys）
    
    Args:
        params: 原始参数
        
    Returns:
        签名后的参数
    """
    img_key, sub_key = await get_wbi_keys()
    return enc_wbi(params, img_key, sub_key)
