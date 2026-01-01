"""
Live Report Generator
Generates visual live stream report images
Simplified and ported from StarBot's LiveReportGenerator
"""

import io
import base64
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

try:
    import jieba
except ImportError:
    jieba = None

try:
    from wordcloud import WordCloud
except ImportError:
    WordCloud = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
except ImportError:
    plt = None

from PIL import Image

from .pic_generator import PicGenerator, Color
from ..core.models import LiveReport


# 停用词
STOP_WORDS = {
    "的", "了", "是", "我", "你", "他", "她", "它", "这", "那",
    "什么", "怎么", "哪", "为什么", "哈哈", "啊", "吧", "呢", "啦",
    "哦", "嗯", "好", "在", "有", "和", "与", "就", "不", "也",
    "还", "吗", "呵呵", "嘿嘿", "哈", "呀", "噢", "喔", "嘛", "哇",
    "真的", "可以", "可能", "应该", "知道", "觉得", "其实", "然后",
}


class LiveReportGenerator:
    """直播报告生成器"""
    
    @classmethod
    def generate(cls, param: Dict[str, Any], config: LiveReport) -> str:
        """
        生成直播报告图片
        
        Args:
            param: 直播报告参数
            config: 直播报告配置
            
        Returns:
            Base64 编码的图片字符串
        """
        width = 1000
        height = 100000  # 高度预设极大，最后裁剪
        top_blank = 75
        margin = 50
        
        generator = PicGenerator(width, height)
        pic = (generator
               .set_pos(margin, top_blank + margin)
               .draw_rounded_rectangle(0, top_blank, width, height - top_blank, 35, Color.WHITE)
               .copy_bottom(35))
        
        # 标题
        pic.draw_chapter("直播报告")
        
        # 主播信息
        uname = param.get('uname', '')
        room_id = param.get('room_id', 0)
        pic.draw_tip(f"{uname} ({room_id})")
        
        # 直播时长
        if config.time:
            start_time = param.get('start_time', '')
            end_time = param.get('end_time', '')
            hour = param.get('hour', 0)
            minute = param.get('minute', 0)
            second = param.get('second', 0)
            
            time_str = ""
            if hour > 0:
                time_str += f"{hour}时 "
            if minute > 0:
                time_str += f"{minute}分 "
            time_str += f"{second}秒"
            
            pic.draw_tip(f"{start_time} ~ {end_time} ({time_str.strip()})")
        
        # 基础数据
        if config.fans_change or config.fans_medal_change or config.guard_change:
            pic.draw_section("基础数据")
            
            if config.fans_change:
                fans_before = param.get('fans_before', -1)
                fans_after = param.get('fans_after', -1)
                if fans_before == -1:
                    fans_before = "?"
                    diff = 0
                else:
                    diff = fans_after - fans_before
                    
                if diff > 0:
                    pic.draw_text([f"粉丝: {fans_before} → {fans_after} ", f"(+{diff})"], [Color.BLACK, Color.RED])
                elif diff < 0:
                    pic.draw_text([f"粉丝: {fans_before} → {fans_after} ", f"({diff})"], [Color.BLACK, Color.GREEN])
                else:
                    pic.draw_text([f"粉丝: {fans_before} → {fans_after} ", f"(+0)"], [Color.BLACK, Color.GRAY])
            
            if config.fans_medal_change:
                medal_before = param.get('fans_medal_before', -1)
                medal_after = param.get('fans_medal_after', -1)
                if medal_before == -1:
                    medal_before = "?"
                    diff = 0
                else:
                    diff = medal_after - medal_before
                    
                if diff > 0:
                    pic.draw_text([f"粉丝团: {medal_before} → {medal_after} ", f"(+{diff})"], [Color.BLACK, Color.RED])
                elif diff < 0:
                    pic.draw_text([f"粉丝团: {medal_before} → {medal_after} ", f"({diff})"], [Color.BLACK, Color.GREEN])
                else:
                    pic.draw_text([f"粉丝团: {medal_before} → {medal_after} ", f"(+0)"], [Color.BLACK, Color.GRAY])
            
            if config.guard_change:
                guard_before = param.get('guard_before', -1)
                guard_after = param.get('guard_after', -1)
                if guard_before == -1:
                    guard_before = "?"
                    diff = 0
                else:
                    diff = guard_after - guard_before
                    
                if diff > 0:
                    pic.draw_text([f"大航海: {guard_before} → {guard_after} ", f"(+{diff})"], [Color.BLACK, Color.RED])
                elif diff < 0:
                    pic.draw_text([f"大航海: {guard_before} → {guard_after} ", f"({diff})"], [Color.BLACK, Color.GREEN])
                else:
                    pic.draw_text([f"大航海: {guard_before} → {guard_after} ", f"(+0)"], [Color.BLACK, Color.GRAY])
        
        # 直播数据
        has_data = config.danmu or config.gift or config.sc or config.box or config.guard
        if has_data:
            pic.draw_section("直播数据")
            
            if config.danmu:
                count = param.get('danmu_count', 0)
                person = param.get('danmu_person_count', 0)
                pic.draw_text(f"弹幕: {count} 条 ({person} 人)")
            
            if config.box:
                count = param.get('box_count', 0)
                profit = param.get('box_profit', 0.0)
                if profit >= 0:
                    pic.draw_text([f"盲盒: {count} 个 ", f"(+{profit:.1f} 元)"], [Color.BLACK, Color.RED])
                else:
                    pic.draw_text([f"盲盒: {count} 个 ", f"({profit:.1f} 元)"], [Color.BLACK, Color.GREEN])
            
            if config.gift:
                profit = param.get('gift_profit', 0.0)
                person = param.get('gift_person_count', 0)
                pic.draw_text(f"礼物: {profit:.1f} 元 ({person} 人)")
            
            if config.sc:
                profit = param.get('sc_profit', 0)
                person = param.get('sc_person_count', 0)
                pic.draw_text(f"SC: {profit} 元 ({person} 人)")
            
            if config.guard:
                captain = param.get('captain_count', 0)
                commander = param.get('commander_count', 0)
                governor = param.get('governor_count', 0)
                total = captain + commander + governor
                if total > 0:
                    parts = []
                    if governor > 0:
                        parts.append(f"总督 {governor}")
                    if commander > 0:
                        parts.append(f"提督 {commander}")
                    if captain > 0:
                        parts.append(f"舰长 {captain}")
                    pic.draw_text(f"大航海: {total} ({', '.join(parts)})")
        
        # 排行榜
        cls._draw_rankings(pic, param, config)
        
        # 曲线图
        cls._draw_diagrams(pic, param, config)
        
        # 弹幕词云
        if config.danmu_cloud:
            cls._draw_word_cloud(pic, param)
        
        # 裁剪并返回
        pic.crop_and_paste_bottom()
        return pic.base64()
    
    @classmethod
    def _draw_rankings(cls, pic: PicGenerator, param: Dict[str, Any], config: LiveReport):
        """绘制排行榜"""
        rankings = []
        
        if config.danmu_ranking > 0:
            data = param.get('danmu_ranking', [])
            if data:
                rankings.append(("弹幕排行", data[:config.danmu_ranking], "条"))
        
        if config.gift_ranking > 0:
            data = param.get('gift_ranking', [])
            if data:
                rankings.append(("礼物排行", data[:config.gift_ranking], "元"))
        
        if config.sc_ranking > 0:
            data = param.get('sc_ranking', [])
            if data:
                rankings.append(("SC排行", data[:config.sc_ranking], "元"))
        
        if not rankings:
            return
        
        pic.draw_section("排行榜")
        
        for title, data, unit in rankings:
            pic.draw_text(f"{title}:")
            for i, (uid, value) in enumerate(data, 1):
                if isinstance(value, float):
                    pic.draw_text(f"  {i}. UID:{uid} - {value:.1f} {unit}")
                else:
                    pic.draw_text(f"  {i}. UID:{uid} - {value} {unit}")
    
    @classmethod
    def _draw_diagrams(cls, pic: PicGenerator, param: Dict[str, Any], config: LiveReport):
        """绘制曲线图"""
        if plt is None:
            return
        
        diagrams = []
        
        if config.box_profit_diagram:
            data = param.get('box_profit_diagram', [])
            if data:
                diagrams.append(("盲盒盈亏曲线", data, "元"))
        
        if config.danmu_diagram:
            data = param.get('danmu_diagram', [])
            if data:
                diagrams.append(("弹幕互动曲线", [d[1] for d in data], "条"))
        
        if not diagrams:
            return
        
        pic.draw_section("互动曲线")
        
        for title, data, unit in diagrams:
            try:
                fig, ax = plt.subplots(figsize=(8, 3), dpi=100)
                ax.plot(range(len(data)), data, 'b-', linewidth=1.5)
                ax.set_title(title, fontsize=12)
                ax.set_ylabel(unit, fontsize=10)
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
                ax.grid(True, alpha=0.3)
                
                # 保存为图片
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
                buf.seek(0)
                plt.close(fig)
                
                # 绘制到报告
                chart_img = Image.open(buf)
                pic.draw_img(chart_img)
            except Exception:
                pass
    
    @classmethod
    def _draw_word_cloud(cls, pic: PicGenerator, param: Dict[str, Any]):
        """绘制弹幕词云"""
        if WordCloud is None or jieba is None:
            return
        
        danmu_list = param.get('all_danmu', [])
        if not danmu_list or len(danmu_list) < 10:
            return
        
        try:
            # 分词
            text = " ".join(danmu_list)
            words = jieba.cut(text)
            words = [w for w in words if len(w) > 1 and w not in STOP_WORDS]
            
            if len(words) < 10:
                return
            
            pic.draw_section("弹幕词云")
            
            # 生成词云
            word_freq = {}
            for w in words:
                word_freq[w] = word_freq.get(w, 0) + 1
            
            wc = WordCloud(
                width=800,
                height=400,
                background_color='white',
                max_words=100,
                prefer_horizontal=0.7,
                min_font_size=10,
                max_font_size=100,
            )
            wc.generate_from_frequencies(word_freq)
            
            # 转为 PIL Image
            wc_img = wc.to_image()
            pic.draw_img(wc_img)
            
        except Exception:
            pass
