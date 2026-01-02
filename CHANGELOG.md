# Changelog

All notable changes to this project will be documented in this file.

## [v1.0.3] - 2026-01-02

### 修复
- 修复 `credential.py` 中 UID 获取时 credential 参数传递错误的问题
- 修复插件关闭时网络 session 资源未释放的问题

## [v1.0.2] - 2026-01-02

### 修复
- 修复 Docker/Linux 环境下 matplotlib 图表无法显示中文（如"盲盒盈亏曲线"、"弹幕互动曲线"）的问题
- 修复弹幕词云无法显示中文的问题
- 修复粉丝/粉丝团/大航海数获取失败时显示为"? → -1"的问题，现在正确显示为"? → ?"

### 变更
- matplotlib 图表现在使用插件自带字体 (`resources/normal.ttf`) 渲染
- WordCloud 弹幕词云现在使用插件自带字体支持中文
- 添加 Linux 兼容的字体回退列表（文泉驿、Droid Sans 等）

## [v1.0.1] - 2026-01-01

### 修复
- 修复粉丝勋章 API 404 错误，使用正确的端点 `/fansMedal/fans_medal_info`
- 使用 asyncio.Lock 和内存标志修复重复开播通知问题
- 修复封面图片显示为 CQ 码文本的问题，现在使用 Image 组件
- 修复报告中中文字符显示为方框的问题，添加中文字体

### 新增
- 添加订阅持久化，重启后自动恢复监控的直播间
- 添加测试脚本 `tests/test_live_report.py` 用于验证报告渲染
- 添加中文字体文件 (`resources/normal.ttf`, `resources/bold.ttf`)
- 添加 `requirements.txt` 依赖清单

### 变更
- 更新 `pic_generator.py` 使用中文兼容字体
- 更新 `get_fans_medal_info` 参数以匹配 StarBot 实现
- 更新会话 ID 格式，使用 'default' 作为平台 ID

## [v1.0.0] - 2025-12-31

### 首次发布
- 开播/下播提醒
- 直播报告生成与数据统计
- 弹幕词云支持
- 基于 SQLite 的数据存储与内存缓冲
