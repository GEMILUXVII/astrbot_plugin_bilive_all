# AstrBot B站直播全功能插件

B站直播监控插件，支持开播/下播提醒和直播数据统计报告。

## 功能特性

- 🔔 **开播提醒** - 主播开播时自动推送通知
- 📊 **下播报告** - 直播结束后生成详细数据报告
  - 粉丝/粉丝团/大航海变动统计
  - 弹幕/礼物/SC/大航海数据
  - 各类排行榜
  - 互动曲线图
  - 弹幕词云
- ⚡ **高性能** - SQLite + 内存缓冲，无需额外服务

## 安装

1. 将插件目录放入 AstrBot 的 `data/plugins/` 目录
2. 重启 AstrBot
3. 使用命令配置监控

## 配置

在 AstrBot 配置面板中填写以下可选配置：

```yaml
# B站账号凭据（可选，用于获取更多信息）
sessdata: ""
bili_jct: ""
buvid3: ""

# 预设房间列表（可选）
rooms:
  - uid: 123456  # 主播 UID
    targets:
      - id: 群号或QQ号
        type: group  # group 或 friend
        live_on: true
        live_off: true
        live_report: true
```

## 命令

| 命令 | 说明 |
|------|------|
| `/bilive add <uid>` | 添加主播监控 |
| `/bilive remove <uid>` | 移除主播监控 |
| `/bilive list` | 列出监控中的主播 |
| `/bilive status` | 查看插件状态 |

## 依赖

- aiohttp
- brotli
- pillow
- wordcloud
- jieba
- matplotlib
- scipy
- pydantic
- aiosqlite

## 许可证

MIT License
