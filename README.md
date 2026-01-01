<div align="center">
  <img src="logo.png" alt="BiliLive All Plugin Logo" width="160" />
</div>

# <div align="center">BiliLive All</div>

<div align="center">
  <strong>B站直播全功能监控插件</strong>
</div>

<br>
<div align="center">
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/VERSION-v1.0.1-E91E63?style=for-the-badge" alt="Version"></a>
  <a href="https://github.com/GEMILUXVII/astrbot_plugin_bilive_all/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-009688?style=for-the-badge" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/PYTHON-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/AstrBotDevs/AstrBot"><img src="https://img.shields.io/badge/AstrBot-Compatible-00BFA5?style=for-the-badge&logo=robot&logoColor=white" alt="AstrBot Compatible"></a>
</div>

<div align="center">
  <a href="https://github.com/botuniverse/onebot-11"><img src="https://img.shields.io/badge/OneBotv11-AIOCQHTTP-FF5722?style=for-the-badge&logo=qq&logoColor=white" alt="OneBot v11 Support"></a>
  <a href="https://github.com/GEMILUXVII/astrbot_plugin_bilive_all"><img src="https://img.shields.io/badge/UPDATED-2026.01.01-2196F3?style=for-the-badge" alt="Updated"></a>
</div>

## 介绍

BiliLive All 是一个基于 AstrBot 开发的 B站直播监控插件，支持开播/下播提醒、直播数据统计报告、弹幕词云生成。

基于 StarBot 核心逻辑移植，针对 AstrBot 平台优化，使用纯 Python 实现，无需额外服务。

## 功能特性

### 核心功能

- **开播提醒** - 主播开播时自动推送通知 + 封面图片
- **下播提醒** - 主播下播时推送通知
- **直播报告** - 直播结束后生成详细数据统计报告
- **持久化存储** - 订阅信息自动保存，重启后自动恢复

### 直播报告内容

- **基础数据** - 粉丝/粉丝团/大航海变动统计
- **互动统计** - 弹幕/礼物/SC/大航海数据
- **排行榜** - 弹幕排行、礼物排行、SC排行
- **可视化** - 互动曲线图、弹幕词云

### 高级功能

- **多房间监控** - 同时监控多个主播
- **灵活配置** - 可单独配置每个推送目标的功能开关
- **高性能** - SQLite + 内存缓冲，支持高并发弹幕处理

## 安装方法

### 1. 下载插件

将插件下载到 AstrBot 的插件目录 `data/plugins/`

### 2. 安装依赖

```bash
cd data/plugins/astrbot_plugin_bilive_all
pip install -r requirements.txt
```

**必须安装的依赖：**

| 依赖 | 用途 |
| --- | --- |
| `aiohttp>=3.8.0` | WebSocket 连接 |
| `aiosqlite>=0.17.0` | 数据库存储 |
| `Pillow>=9.0.0` | 图片处理 |

**可选依赖：**

| 依赖 | 用途 |
| --- | --- |
| `wordcloud>=1.8.0` | 弹幕词云 |
| `jieba>=0.42.0` | 中文分词 |
| `matplotlib>=3.5.0` | 互动曲线图 |

### 3. 重启 AstrBot

确保插件被正确加载。

### 4. 配置插件

在 AstrBot 管理面板的「插件配置」中设置选项。

## 命令列表

### 监控管理

#### `*bilive_add <UID>`
添加主播监控到当前群。

```
*bilive_add 403039446
```

- 添加成功后会自动保存，重启后自动恢复监控

---

#### `*bilive_rm <UID>`
移除主播监控。

```
*bilive_rm 403039446
```

---

#### `*bilive_list`
列出当前监控的所有主播。

```
*bilive_list
```

---

#### `*bilive_status`
查看插件运行状态。

```
*bilive_status
```

- 显示 WebSocket 连接状态、监控房间数等信息

## 配置说明

所有配置可在 AstrBot 管理面板中修改：

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `sessdata` | B站登录凭据 SESSDATA | 空 |
| `bili_jct` | B站登录凭据 bili_jct | 空 |
| `buvid3` | B站设备标识 buvid3 | 空 |
| `live_on_enabled` | 默认启用开播通知 | `true` |
| `live_off_enabled` | 默认启用下播通知 | `true` |
| `live_report_enabled` | 默认启用直播报告 | `true` |
| `live_on_message` | 开播通知模板 | `{uname} 正在直播 {title}\n{url}` |
| `live_off_message` | 下播通知模板 | `{uname} 直播结束了` |
| `report_fans_change` | 报告显示粉丝变动 | `true` |
| `report_danmu` | 报告显示弹幕统计 | `true` |
| `report_gift` | 报告显示礼物统计 | `true` |
| `report_sc` | 报告显示SC统计 | `true` |
| `report_guard` | 报告显示大航海 | `true` |
| `report_ranking` | 排行榜显示数量 | `3` |
| `report_wordcloud` | 报告显示弹幕词云 | `true` |
| `report_diagram` | 报告显示互动曲线 | `true` |
| `debug_mode` | 调试模式 | `false` |

> [!TIP]
> B站凭据用于 WebSocket 认证和获取更详细的直播数据。不填写也能使用基本功能，但推荐填写以获得更好的体验。

> [!NOTE]
> 监控房间通过 `*bilive_add` 命令添加，数据会自动持久化保存，重启后自动恢复。

## 文件结构

```
astrbot_plugin_bilive_all/
├── main.py              # 插件入口和命令注册
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置模式定义
├── requirements.txt     # 依赖库列表
├── resources/           # 资源文件
│   ├── normal.ttf       # 中文字体
│   └── bold.ttf         # 中文粗体
├── core/                # 核心模块
│   ├── live_danmaku.py  # WebSocket 弹幕连接
│   ├── live_room.py     # 直播间 API
│   ├── room_monitor.py  # 房间监控器
│   └── models.py        # 数据模型
├── painter/             # 绘图模块
│   ├── pic_generator.py # 图片生成器
│   └── live_report.py   # 直播报告生成
├── storage/             # 存储模块
│   └── stats_db.py      # 数据库操作
└── utils/               # 工具模块
    ├── credential.py    # 凭据管理
    ├── network.py       # 网络请求
    └── wbi.py           # WBI 签名
```

## 常见问题

### Q: WebSocket 连接失败？

**A:** 请检查 B站凭据是否正确配置。建议填写 `sessdata`、`bili_jct` 和 `buvid3`。

### Q: 报告中文显示为方块？

**A:** 确保 `resources/` 目录下有 `normal.ttf` 和 `bold.ttf` 字体文件。

### Q: 开播通知重复发送？

**A:** v1.0.1 已修复此问题，请更新到最新版本。

## 更新日志

查看完整更新日志：[CHANGELOG.md](./CHANGELOG.md)

**当前版本：v1.0.1** - 修复多项问题，添加订阅持久化功能。

## 注意事项

- 本插件仅供学习交流使用
- 请勿滥用 B站 API
- 请遵守当地法律法规

## 许可证

[![](https://www.gnu.org/graphics/agplv3-155x51.png "AGPL v3 logo")](https://www.gnu.org/licenses/agpl-3.0.txt)

Copyright (C) 2026 GEMILUXVII

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

## 致谢

本项目基于或参考了以下开源项目:

- [StarBot](https://github.com/Starlwr/StarBot) - 核心逻辑参考
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 机器人框架
