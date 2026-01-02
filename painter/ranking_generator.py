"""
排行榜图片生成器
"""

from PIL import Image, ImageDraw

from ..utils.user_info import mask_round
from .pic_generator import Color, PicGenerator


class RankingGenerator:
    """排行榜图片生成器"""

    @classmethod
    def _get_rank_bar_pic(
        cls,
        width: int,
        height: int,
        start_color: tuple[int, int, int] = (57, 119, 230),
        end_color: tuple[int, int, int] = (55, 187, 248),
        reverse: bool = False,
    ) -> Image.Image:
        """
        生成排行榜中渐变排行条图片

        Args:
            width: 排行条长度
            height: 排行条宽度
            start_color: 渐变起始颜色
            end_color: 渐变终止颜色
            reverse: 是否生成反向排行条
        """
        if reverse:
            start_color, end_color = end_color, start_color

        r_step = (end_color[0] - start_color[0]) / max(width, 1)
        g_step = (end_color[1] - start_color[1]) / max(width, 1)
        b_step = (end_color[2] - start_color[2]) / max(width, 1)

        now_color = list(start_color)

        bar = Image.new("RGBA", (width, 1))
        draw = ImageDraw.Draw(bar)

        for i in range(width):
            draw.point((i, 0), (int(now_color[0]), int(now_color[1]), int(now_color[2])))
            now_color[0] += r_step
            now_color[1] += g_step
            now_color[2] += b_step

        bar = bar.resize((width, height))

        # 添加斜边裁切蒙版
        mask = Image.new("L", (width, height), 255)
        mask_draw = ImageDraw.Draw(mask)
        if not reverse:
            mask_draw.polygon(((width - height, height), (width, 0), (width, height)), 0)
        else:
            mask_draw.polygon(((0, 0), (0, height), (height, height)), 0)
        bar.putalpha(mask)
        mask.close()

        return bar

    @classmethod
    def get_ranking(
        cls,
        row_space: int,
        faces: list[Image.Image],
        unames: list[str],
        counts: list[int | float],
        width: int,
        top_count: int | float | None = None,
        start_color: tuple[int, int, int] = (57, 119, 230),
        end_color: tuple[int, int, int] = (55, 187, 248),
    ) -> Image.Image:
        """
        绘制排行榜

        Args:
            row_space: 行间距
            faces: 头像图片列表，按数量降序排序
            unames: 昵称列表，按数量降序排序
            counts: 数量列表，降序排序
            width: 排行榜图片宽度
            top_count: 第一名数量，后续排行条基于此计算长度
            start_color: 渐变起始颜色
            end_color: 渐变终止颜色
        """
        count = len(counts)
        if count == 0:
            return Image.new("RGBA", (width, 1))

        if len(faces) != len(unames) or len(unames) != len(counts):
            raise ValueError("绘制排行榜错误, 头像昵称列表与数量列表长度不匹配")

        face_size = 100
        offset = 10
        bar_height = 30

        bar_x = face_size - offset
        top_bar_width = width - face_size + offset
        if top_count is None:
            top_count = counts[0] if counts[0] != 0 else 1

        chart = PicGenerator(width, (face_size * count) + (row_space * (count - 1)))
        chart.set_row_space(row_space)

        for i in range(count):
            bar_width = int(counts[i] / top_count * top_bar_width) if top_count != 0 else 0
            if bar_width > 0:
                bar = cls._get_rank_bar_pic(bar_width, bar_height, start_color, end_color)
                chart.draw_img_alpha(bar, (bar_x, chart.y + int((face_size - bar_height) / 2)))

            # 绘制昵称
            chart.draw_tip(unames[i], Color.BLACK, (bar_x + (offset * 2), chart.y))

            # 绘制数量
            uname_len = chart.get_tip_length(unames[i])
            count_x = max(chart.x + bar_width, bar_x + (offset * 3) + uname_len)
            count_str = str(int(counts[i])) if isinstance(counts[i], float) and counts[i] == int(counts[i]) else str(counts[i])
            chart.draw_tip(count_str, Color.GRAY, (count_x, chart.y))

            # 绘制头像
            face_img = faces[i].resize((face_size, face_size)).convert("RGBA")
            chart.draw_img_alpha(mask_round(face_img))

        return chart.img

    @classmethod
    def get_double_ranking(
        cls,
        row_space: int,
        faces: list[Image.Image],
        unames: list[str],
        counts: list[int | float],
        width: int,
        top_count: int | float | None = None,
        start_color: tuple[int, int, int] = (230, 57, 70),
        end_color: tuple[int, int, int] = (248, 150, 150),
        reverse_start_color: tuple[int, int, int] = (57, 180, 80),
        reverse_end_color: tuple[int, int, int] = (120, 220, 140),
    ) -> Image.Image:
        """
        绘制双向排行榜（用于盈亏显示）

        Args:
            row_space: 行间距
            faces: 头像图片列表
            unames: 昵称列表
            counts: 数量列表（可包含负数）
            width: 排行榜图片宽度
            top_count: 最大绝对值，用于计算排行条长度
            start_color: 正向渐变起始颜色
            end_color: 正向渐变终止颜色
            reverse_start_color: 反向渐变起始颜色
            reverse_end_color: 反向渐变终止颜色
        """
        count = len(counts)
        if count == 0:
            return Image.new("RGBA", (width, 1))

        if len(faces) != len(unames) or len(unames) != len(counts):
            raise ValueError("绘制排行榜错误, 头像昵称列表与数量列表长度不匹配")

        face_size = 100
        offset = 10
        bar_height = 30

        face_x = int((width - face_size) / 2)
        bar_x = face_x + face_size - offset
        reverse_bar_x = face_x + offset
        top_bar_width = (width - face_size) / 2 + offset

        if top_count is None:
            top_count = max(max(counts), abs(min(counts))) if counts else 1
        if top_count == 0:
            top_count = 1

        chart = PicGenerator(width, (face_size * count) + (row_space * (count - 1)))
        chart.set_row_space(row_space)

        for i in range(count):
            bar_width = int(abs(counts[i]) / top_count * top_bar_width)

            if bar_width > 0:
                if counts[i] > 0:
                    bar = cls._get_rank_bar_pic(bar_width, bar_height, start_color, end_color)
                    chart.draw_img_alpha(bar, (bar_x, chart.y + int((face_size - bar_height) / 2)))
                elif counts[i] < 0:
                    bar = cls._get_rank_bar_pic(bar_width, bar_height, reverse_start_color, reverse_end_color, True)
                    chart.draw_img_alpha(bar, (reverse_bar_x - bar_width, chart.y + int((face_size - bar_height) / 2)))

            # 绘制昵称和数量
            count_str = f"+{counts[i]}" if counts[i] > 0 else str(counts[i])
            if counts[i] >= 0:
                chart.draw_tip(unames[i], Color.BLACK, (bar_x + (offset * 2), chart.y))
                uname_len = chart.get_tip_length(unames[i])
                count_x = max(face_x + bar_width, bar_x + (offset * 3) + uname_len)
                chart.draw_tip(count_str, Color.RED if counts[i] > 0 else Color.GRAY, (count_x, chart.y))
            else:
                uname_len = chart.get_tip_length(unames[i])
                count_len = chart.get_tip_length(count_str)
                chart.draw_tip(unames[i], Color.BLACK, (reverse_bar_x - (offset * 2) - uname_len, chart.y))
                count_x = min(face_x + face_size - bar_width - count_len, reverse_bar_x - (offset * 3) - uname_len - count_len)
                chart.draw_tip(count_str, Color.GREEN, (count_x, chart.y))

            # 绘制头像（居中）
            chart.set_pos(x=face_x)
            face_img = faces[i].resize((face_size, face_size)).convert("RGBA")
            chart.draw_img_alpha(mask_round(face_img))
            chart.set_pos(x=0)

        return chart.img
