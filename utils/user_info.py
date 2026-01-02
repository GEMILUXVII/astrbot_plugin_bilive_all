"""
用户信息工具模块 - 批量获取用户昵称和头像
"""
import asyncio
import os
from io import BytesIO

from PIL import Image, ImageDraw

from .credential import credential_manager
from .network import get_session, request


def split_list(lst: list, n: int) -> list[list]:
    """将列表分割为每组 n 个元素的子列表"""
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def mask_round(img: Image.Image) -> Image.Image:
    """将图片转换为圆形"""
    mask = Image.new("L", img.size)
    mask_draw = ImageDraw.Draw(mask)
    img_width, img_height = img.size
    mask_draw.ellipse((0, 0, img_width, img_height), fill=255)
    img.putalpha(mask)
    mask.close()
    return img


def limit_str_length(origin_str: str, limit: int) -> str:
    """限制字符串最大长度，超出部分截去并添加 '...'"""
    return f"{origin_str[:limit]}..." if len(origin_str) > limit else origin_str


async def open_url_image(url: str) -> Image.Image | None:
    """读取网络图片"""
    if not url:
        return None

    try:
        session = await get_session()
        async with session.get(url) as response:
            image_data = await response.read()
            return Image.open(BytesIO(image_data))
    except Exception:
        return None


def get_default_face() -> Image.Image:
    """获取默认头像"""
    resource_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "face.png")
    if os.path.exists(resource_path):
        return Image.open(resource_path).convert("RGBA")
    # 如果没有默认头像，创建一个灰色圆形
    size = 100
    img = Image.new("RGBA", (size, size), (200, 200, 200, 255))
    return mask_round(img)


async def get_unames_and_faces_by_uids(uids: list[str]) -> tuple[list[str], list[Image.Image]]:
    """
    根据 UID 列表批量获取昵称和头像图片

    Args:
        uids: UID 列表 (字符串)

    Returns:
        昵称列表和头像图片列表组成的元组
    """
    if not uids:
        return [], []

    infos_list = []
    uid_lists = split_list(uids, 10)

    for lst in uid_lists:
        user_info_url = f"https://api.vc.bilibili.com/account/v1/user/cards?uids={','.join(lst)}"
        try:
            result = await request("GET", user_info_url, credential=credential_manager)
            if isinstance(result, list):
                infos_list.extend(result)
        except Exception:
            # 请求失败，返回错误占位符
            failed_unames = [f"用户{uid}" for uid in uids]
            failed_faces = [get_default_face() for _ in uids]
            return failed_unames, failed_faces

    # 构建 UID -> info 映射
    infos = {x["mid"]: x for x in infos_list}

    # 获取昵称列表
    unames = []
    for uid in uids:
        uid_int = int(uid)
        if uid_int in infos:
            unames.append(infos[uid_int].get("name", f"用户{uid}"))
        else:
            unames.append(f"用户{uid}")

    # 并行下载头像
    async def download_face(uid: str) -> Image.Image:
        uid_int = int(uid)
        if uid_int in infos and infos[uid_int].get("face"):
            face = await open_url_image(infos[uid_int]["face"])
            if face:
                return face.convert("RGBA")
        return get_default_face()

    faces = await asyncio.gather(*[download_face(uid) for uid in uids])
    return unames, list(faces)
