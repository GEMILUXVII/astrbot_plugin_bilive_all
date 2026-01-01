# Changelog

All notable changes to this project will be documented in this file.

## [v1.0.1] - 2026-01-01

### Fixed
- Fixed fans medal API 404 error by using correct endpoint `/fansMedal/fans_medal_info`
- Fixed duplicate live notifications with asyncio.Lock and in-memory flag
- Fixed cover image displaying as CQ code text, now uses Image component
- Fixed Chinese characters rendering as boxes in reports, added Chinese fonts

### Added
- Added subscription persistence, auto-restore monitored rooms on restart
- Added test script `tests/test_live_report.py` for report rendering verification
- Added Chinese font files (`resources/normal.ttf`, `resources/bold.ttf`)
- Added `requirements.txt` with all dependencies

### Changed
- Updated `pic_generator.py` to use Chinese-compatible fonts
- Updated `get_fans_medal_info` params to match StarBot implementation
- Updated session ID format to use 'default' as platform ID

## [v1.0.0] - 2025-12-31

### Initial Release
- Live stream start/end notifications
- Live report generation with statistics
- Danmu word cloud support
- SQLite-based data storage with memory buffering
