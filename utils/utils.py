"""
Common utility functions
"""

import time
from datetime import datetime
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw


def timestamp_format(timestamp: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳"""
    return datetime.fromtimestamp(timestamp).strftime(fmt)


def split_list(lst: List, n: int) -> List[List]:
    """将列表分割成每组 n 个元素"""
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def limit_str_length(s: str, max_len: int) -> str:
    """限制字符串长度"""
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"


def mask_round(img: Image.Image) -> Image.Image:
    """将图片裁剪为圆形"""
    size = img.size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result


def format_duration(seconds: int) -> str:
    """格式化时长"""
    minute, second = divmod(seconds, 60)
    hour, minute = divmod(minute, 60)
    
    parts = []
    if hour > 0:
        parts.append(f"{hour}时")
    if minute > 0:
        parts.append(f"{minute}分")
    if second > 0 or not parts:
        parts.append(f"{second}秒")
    
    return " ".join(parts)
