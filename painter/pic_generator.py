"""
Picture Generator for Live Report
Ported and simplified from StarBot's PicGenerator
"""

import base64
import os
from enum import Enum
from io import BytesIO
from typing import Optional, Union, Tuple, List
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class Color(Enum):
    """常用颜色 RGB 枚举"""
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    GRAY = (169, 169, 169)
    LIGHTGRAY = (244, 244, 244)
    RED = (150, 0, 0)
    GREEN = (0, 150, 0)
    DEEPBLUE = (55, 187, 248)
    LIGHTBLUE = (175, 238, 238)
    DEEPRED = (240, 128, 128)
    LIGHTRED = (255, 220, 220)
    DEEPGREEN = (0, 255, 0)
    LIGHTGREEN = (184, 255, 184)
    CRIMSON = (220, 20, 60)       # 总督红
    FUCHSIA = (255, 0, 255)       # 提督紫
    DEEPSKYBLUE = (0, 191, 255)   # 舰长蓝
    LINK = (23, 139, 207)
    PINK = (251, 114, 153)


# 默认字体路径
RESOURCE_DIR = Path(__file__).parent.parent / "resources"


def get_font_path(font_name: str) -> str:
    """获取字体路径"""
    font_path = RESOURCE_DIR / "fonts" / font_name
    if font_path.exists():
        return str(font_path)
    # 尝试使用系统字体
    return font_name


class PicGenerator:
    """
    基于 Pillow 的绘图器，支持链式调用
    """
    
    # 默认配置
    DEFAULT_FONT = "LXGWWenKai-Regular.ttf"
    COVER_MARGIN = 25
    
    def __init__(
        self,
        width: int,
        height: int,
        font_path: Optional[str] = None
    ):
        """
        初始化绘图器
        
        Args:
            width: 画布宽度
            height: 画布高度
            font_path: 字体路径
        """
        self._width = width
        self._height = height
        self._canvas = Image.new("RGBA", (width, height))
        self._draw = ImageDraw.Draw(self._canvas)
        
        # 加载字体
        font_file = font_path or get_font_path(self.DEFAULT_FONT)
        try:
            self._chapter_font = ImageFont.truetype(font_file, 50)
            self._section_font = ImageFont.truetype(font_file, 40)
            self._tip_font = ImageFont.truetype(font_file, 25)
            self._text_font = ImageFont.truetype(font_file, 30)
        except Exception:
            # 使用默认字体
            self._chapter_font = ImageFont.load_default()
            self._section_font = ImageFont.load_default()
            self._tip_font = ImageFont.load_default()
            self._text_font = ImageFont.load_default()
        
        self._xy = (0, 0)
        self._row_space = 25
        self._bottom_pic: Optional[Image.Image] = None
    
    @property
    def width(self) -> int:
        return self._width
    
    @property
    def height(self) -> int:
        return self._height
    
    @property
    def x(self) -> int:
        return self._xy[0]
    
    @property
    def y(self) -> int:
        return self._xy[1]
    
    @property
    def xy(self) -> Tuple[int, int]:
        return self._xy
    
    @property
    def row_space(self) -> int:
        return self._row_space
    
    @property
    def img(self) -> Image.Image:
        return self._canvas
    
    def set_row_space(self, row_space: int) -> "PicGenerator":
        """设置行距"""
        self._row_space = row_space
        return self
    
    def set_pos(self, x: Optional[int] = None, y: Optional[int] = None) -> "PicGenerator":
        """设置绘图坐标"""
        x = x if x is not None else self.x
        y = y if y is not None else self.y
        self._xy = (x, y)
        return self
    
    def move_pos(self, x: int, y: int) -> "PicGenerator":
        """移动绘图坐标"""
        self._xy = (self.x + x, self.y + y)
        return self
    
    def copy_bottom(self, height: int) -> "PicGenerator":
        """拷贝画布底部"""
        self._bottom_pic = self._canvas.crop((0, self.height - height, self.width, self.height))
        return self
    
    def crop_and_paste_bottom(self) -> "PicGenerator":
        """裁剪并粘贴底部"""
        if self._bottom_pic is None:
            self._canvas = self._canvas.crop((0, 0, self.width, self.y))
            return self
        
        self._canvas = self._canvas.crop((0, 0, self.width, self.y + self._bottom_pic.height))
        self._canvas.paste(self._bottom_pic, (0, self.y))
        return self
    
    def draw_rectangle(
        self,
        x: int, y: int,
        width: int, height: int,
        color: Union[Color, Tuple[int, int, int]]
    ) -> "PicGenerator":
        """绘制矩形"""
        if isinstance(color, Color):
            color = color.value
        self._draw.rectangle(((x, y), (x + width, y + height)), color)
        return self
    
    def draw_rounded_rectangle(
        self,
        x: int, y: int,
        width: int, height: int,
        radius: int,
        color: Union[Color, Tuple[int, int, int]]
    ) -> "PicGenerator":
        """绘制圆角矩形"""
        if isinstance(color, Color):
            color = color.value
        self._draw.rounded_rectangle(((x, y), (x + width, y + height)), radius, color)
        return self
    
    def auto_size_img_by_limit(
        self,
        img: Image.Image,
        xy_limit: Tuple[int, int],
        xy: Optional[Tuple[int, int]] = None
    ) -> Image.Image:
        """限制图片不覆盖指定点"""
        if xy is None:
            xy = self._xy
        
        cover_limit = (xy_limit[0] - self.COVER_MARGIN, xy_limit[1] + self.COVER_MARGIN)
        x_cover = xy[0] + img.width - cover_limit[0]
        
        if xy[1] >= cover_limit[1] or x_cover <= 0:
            return img
        
        new_width = img.width - x_cover
        new_height = int(img.height * (new_width / img.width))
        return img.resize((new_width, new_height))
    
    def draw_img(
        self,
        img: Union[str, Image.Image],
        xy: Optional[Tuple[int, int]] = None
    ) -> "PicGenerator":
        """绘制图片"""
        if isinstance(img, str):
            img = Image.open(img)
        
        if xy is None:
            self._canvas.paste(img, self._xy)
            self.move_pos(0, img.height + self._row_space)
        else:
            self._canvas.paste(img, xy)
        
        return self
    
    def draw_img_alpha(
        self,
        img: Union[str, Image.Image],
        xy: Optional[Tuple[int, int]] = None
    ) -> "PicGenerator":
        """绘制透明图片"""
        if isinstance(img, str):
            img = Image.open(img)
        
        if xy is None:
            self._canvas.paste(img, self._xy, img)
            self.move_pos(0, img.height + self._row_space)
        else:
            self._canvas.paste(img, xy, img)
        
        return self
    
    def draw_img_with_border(
        self,
        img: Union[str, Image.Image],
        xy: Optional[Tuple[int, int]] = None,
        color: Union[Color, Tuple[int, int, int]] = Color.BLACK,
        radius: int = 10,
        width: int = 1
    ) -> "PicGenerator":
        """绘制带边框的图片"""
        if isinstance(img, str):
            img = Image.open(img)
        if isinstance(color, Color):
            color = color.value
        
        if xy is None:
            xy = self._xy
            self.draw_img(img)
        else:
            self.draw_img(img, xy)
        
        border = Image.new("RGBA", (img.width + (width * 2), img.height + (width * 2)))
        ImageDraw.Draw(border).rounded_rectangle(
            (0, 0, img.width, img.height), radius, (0, 0, 0, 0), color, width
        )
        self.draw_img_alpha(border, (xy[0] - width, xy[1] - width))
        return self
    
    def draw_chapter(
        self,
        text: str,
        color: Union[Color, Tuple[int, int, int]] = Color.BLACK,
        xy: Optional[Tuple[int, int]] = None
    ) -> "PicGenerator":
        """绘制章节标题"""
        if isinstance(color, Color):
            color = color.value
        
        if xy is None:
            self._draw.text(self._xy, text, color, self._chapter_font)
            self.move_pos(0, 50 + self._row_space)
        else:
            self._draw.text(xy, text, color, self._chapter_font)
        return self
    
    def draw_section(
        self,
        text: str,
        color: Union[Color, Tuple[int, int, int]] = Color.BLACK,
        xy: Optional[Tuple[int, int]] = None
    ) -> "PicGenerator":
        """绘制小节标题"""
        if isinstance(color, Color):
            color = color.value
        
        if xy is None:
            self._draw.text(self._xy, text, color, self._section_font)
            self.move_pos(0, 40 + self._row_space)
        else:
            self._draw.text(xy, text, color, self._section_font)
        return self
    
    def draw_tip(
        self,
        text: str,
        color: Union[Color, Tuple[int, int, int]] = Color.GRAY,
        xy: Optional[Tuple[int, int]] = None
    ) -> "PicGenerator":
        """绘制提示文本"""
        if isinstance(color, Color):
            color = color.value
        
        if xy is None:
            self._draw.text(self._xy, text, color, self._tip_font)
            self.move_pos(0, 25 + self._row_space)
        else:
            self._draw.text(xy, text, color, self._tip_font)
        return self
    
    def draw_text(
        self,
        texts: Union[str, List[str]],
        colors: Optional[Union[Color, Tuple[int, int, int], List[Union[Color, Tuple[int, int, int]]]]] = None,
        xy: Optional[Tuple[int, int]] = None
    ) -> "PicGenerator":
        """绘制文本"""
        if colors is None:
            colors = []
        if isinstance(texts, str):
            texts = [texts]
        if isinstance(colors, (Color, tuple)):
            colors = [colors]
        
        # 补齐颜色
        for _ in range(len(texts) - len(colors)):
            colors.append(Color.BLACK)
        
        # 转换颜色
        colors = [c.value if isinstance(c, Color) else c for c in colors]
        
        if xy is None:
            x = self.x
            for i, text in enumerate(texts):
                self._draw.text(self._xy, text, colors[i], self._text_font)
                text_len = int(self._draw.textlength(text, self._text_font))
                self.move_pos(text_len, 0)
            self.move_pos(x - self.x, 30 + self._row_space)
        else:
            for i, text in enumerate(texts):
                self._draw.text(xy, text, colors[i], self._text_font)
                text_len = int(self._draw.textlength(text, self._text_font))
                xy = (xy[0] + text_len, xy[1])
        return self
    
    def draw_text_right(
        self,
        margin_right: int,
        texts: Union[str, List[str]],
        colors: Optional[Union[Color, Tuple[int, int, int], List[Union[Color, Tuple[int, int, int]]]]] = None,
        xy_limit: Tuple[int, int] = (0, 0)
    ) -> "PicGenerator":
        """绘制右对齐文本"""
        if isinstance(texts, str):
            texts = [texts]
        
        text_len = sum(int(self._draw.textlength(t, self._text_font)) for t in texts)
        x = self.width - text_len - margin_right
        
        cover_limit = (xy_limit[0] - self.COVER_MARGIN, xy_limit[1] + self.COVER_MARGIN)
        y = max(self._xy[1], cover_limit[1])
        
        self.draw_text(texts, colors, (x, y))
        self.set_pos(self._xy[0], y + 30 + self._row_space)
        return self
    
    def get_text_length(self, text: str) -> int:
        """获取文本长度"""
        return int(self._draw.textlength(text, self._text_font))
    
    def base64(self) -> str:
        """获取 Base64 字符串"""
        io = BytesIO()
        self._canvas.save(io, format="PNG")
        return base64.b64encode(io.getvalue()).decode()
    
    def save(self, path: str):
        """保存图片"""
        self._canvas.save(path)
    
    def save_and_get_base64(self, path: str) -> str:
        """保存并获取 Base64"""
        self._canvas.save(path)
        return self.base64()
