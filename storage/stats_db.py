"""
SQLite-based statistics storage with memory buffer
Replaces StarBot's Redis storage with a lightweight SQLite solution
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

import aiosqlite


class StatsBuffer:
    """
    内存缓冲层，用于高频写入场景
    积攒数据后批量写入 SQLite，减少磁盘 I/O
    """
    
    def __init__(self, flush_interval: float = 5.0):
        self.flush_interval = flush_interval
        
        # 房间级计数
        self.room_danmu_count: Dict[int, int] = defaultdict(int)
        self.room_gift_profit: Dict[int, float] = defaultdict(float)
        self.room_sc_profit: Dict[int, int] = defaultdict(int)
        self.room_box_count: Dict[int, int] = defaultdict(int)
        self.room_box_profit: Dict[int, float] = defaultdict(float)
        
        # 大航海计数 (room_id -> {type: count})
        self.room_guard_count: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # 用户级计数 (room_id, uid) -> count
        self.user_danmu_count: Dict[Tuple[int, int], int] = defaultdict(int)
        self.user_gift_profit: Dict[Tuple[int, int], float] = defaultdict(float)
        self.user_sc_profit: Dict[Tuple[int, int], int] = defaultdict(int)
        self.user_box_count: Dict[Tuple[int, int], int] = defaultdict(int)
        self.user_box_profit: Dict[Tuple[int, int], float] = defaultdict(float)
        self.user_guard_count: Dict[Tuple[int, int, str], int] = defaultdict(int)
        
        # 弹幕文本（用于词云）
        self.room_danmu_texts: Dict[int, List[str]] = defaultdict(list)
        
        # 时间分布数据（用于曲线图）
        self.room_danmu_times: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        self.room_gift_times: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
        self.room_sc_times: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        self.room_box_times: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        self.room_guard_times: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        
        # 盲盒盈亏记录
        self.room_box_profit_records: Dict[int, List[float]] = defaultdict(list)
        
        self._flush_task: Optional[asyncio.Task] = None
        self._db: Optional["StatsDB"] = None
    
    def set_db(self, db: "StatsDB"):
        """设置数据库实例"""
        self._db = db
    
    async def start(self):
        """启动定时刷新任务"""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())
    
    async def stop(self):
        """停止定时刷新任务"""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        # 最后刷新一次
        await self.flush()
    
    async def _flush_loop(self):
        """定时刷新循环"""
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.flush()
    
    async def flush(self):
        """将缓冲数据写入数据库"""
        if self._db is None:
            return
        
        await self._db.flush_buffer(self)
        self._clear()
    
    def _clear(self):
        """清空缓冲区"""
        self.room_danmu_count.clear()
        self.room_gift_profit.clear()
        self.room_sc_profit.clear()
        self.room_box_count.clear()
        self.room_box_profit.clear()
        self.room_guard_count.clear()
        self.user_danmu_count.clear()
        self.user_gift_profit.clear()
        self.user_sc_profit.clear()
        self.user_box_count.clear()
        self.user_box_profit.clear()
        self.user_guard_count.clear()
        self.room_danmu_texts.clear()
        self.room_danmu_times.clear()
        self.room_gift_times.clear()
        self.room_sc_times.clear()
        self.room_box_times.clear()
        self.room_guard_times.clear()
        self.room_box_profit_records.clear()
    
    # ===== 写入方法（写入内存缓冲）=====
    
    def incr_danmu(self, room_id: int, uid: int, content: str):
        """增加弹幕计数"""
        self.room_danmu_count[room_id] += 1
        if uid != 0:
            self.user_danmu_count[(room_id, uid)] += 1
        self.room_danmu_texts[room_id].append(content)
        self.room_danmu_times[room_id].append((int(time.time()), 1))
    
    def incr_gift(self, room_id: int, uid: int, profit: float):
        """增加礼物统计"""
        self.room_gift_profit[room_id] += profit
        self.user_gift_profit[(room_id, uid)] += profit
        self.room_gift_times[room_id].append((int(time.time()), profit))
    
    def incr_sc(self, room_id: int, uid: int, price: int):
        """增加SC统计"""
        self.room_sc_profit[room_id] += price
        self.user_sc_profit[(room_id, uid)] += price
        self.room_sc_times[room_id].append((int(time.time()), price))
    
    def incr_box(self, room_id: int, uid: int, count: int, profit: float):
        """增加盲盒统计"""
        self.room_box_count[room_id] += count
        self.user_box_count[(room_id, uid)] += count
        self.room_box_profit[room_id] += profit
        self.user_box_profit[(room_id, uid)] += profit
        self.room_box_times[room_id].append((int(time.time()), count))
        # 记录累计盈亏
        current_total = self.room_box_profit[room_id]
        self.room_box_profit_records[room_id].append(current_total)
    
    def incr_guard(self, room_id: int, uid: int, guard_type: str, months: int):
        """增加大航海统计"""
        self.room_guard_count[room_id][guard_type] += months
        self.user_guard_count[(room_id, uid, guard_type)] += months
        self.room_guard_times[room_id].append((int(time.time()), months))


class StatsDB:
    """
    SQLite 统计数据库
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self.buffer = StatsBuffer()
        self.buffer.set_db(self)
    
    async def init(self):
        """初始化数据库"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        await self._create_tables()
        await self.buffer.start()
    
    async def close(self):
        """关闭数据库连接"""
        await self.buffer.stop()
        if self._conn:
            await self._conn.close()
            self._conn = None
    
    async def _create_tables(self):
        """创建数据表"""
        await self._conn.executescript("""
            -- 直播状态
            CREATE TABLE IF NOT EXISTS live_status (
                room_id INTEGER PRIMARY KEY,
                status INTEGER DEFAULT 0,
                start_time INTEGER DEFAULT 0,
                end_time INTEGER DEFAULT 0
            );
            
            -- 直播场次
            CREATE TABLE IF NOT EXISTS live_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                start_time INTEGER NOT NULL,
                end_time INTEGER DEFAULT 0,
                fans_before INTEGER DEFAULT -1,
                fans_after INTEGER DEFAULT -1,
                fans_medal_before INTEGER DEFAULT -1,
                fans_medal_after INTEGER DEFAULT -1,
                guard_before INTEGER DEFAULT -1,
                guard_after INTEGER DEFAULT -1
            );
            
            -- 房间统计（当前场次累计）
            CREATE TABLE IF NOT EXISTS room_stats (
                room_id INTEGER PRIMARY KEY,
                danmu_count INTEGER DEFAULT 0,
                gift_profit REAL DEFAULT 0,
                sc_profit INTEGER DEFAULT 0,
                box_count INTEGER DEFAULT 0,
                box_profit REAL DEFAULT 0,
                captain_count INTEGER DEFAULT 0,
                commander_count INTEGER DEFAULT 0,
                governor_count INTEGER DEFAULT 0
            );
            
            -- 用户弹幕统计
            CREATE TABLE IF NOT EXISTS user_danmu (
                room_id INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (room_id, uid)
            );
            
            -- 用户礼物统计
            CREATE TABLE IF NOT EXISTS user_gift (
                room_id INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                profit REAL DEFAULT 0,
                PRIMARY KEY (room_id, uid)
            );
            
            -- 用户SC统计
            CREATE TABLE IF NOT EXISTS user_sc (
                room_id INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                profit INTEGER DEFAULT 0,
                PRIMARY KEY (room_id, uid)
            );
            
            -- 用户盲盒统计
            CREATE TABLE IF NOT EXISTS user_box (
                room_id INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                count INTEGER DEFAULT 0,
                profit REAL DEFAULT 0,
                PRIMARY KEY (room_id, uid)
            );
            
            -- 用户大航海统计
            CREATE TABLE IF NOT EXISTS user_guard (
                room_id INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                guard_type TEXT NOT NULL,
                months INTEGER DEFAULT 0,
                PRIMARY KEY (room_id, uid, guard_type)
            );
            
            -- 弹幕文本（用于词云）
            CREATE TABLE IF NOT EXISTS danmu_texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            );
            
            -- 时间分布数据
            CREATE TABLE IF NOT EXISTS time_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                stat_type TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                value REAL NOT NULL
            );
            
            -- 盲盒盈亏记录
            CREATE TABLE IF NOT EXISTS box_profit_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                profit REAL NOT NULL
            );
            
            -- 创建索引
            CREATE INDEX IF NOT EXISTS idx_danmu_texts_room ON danmu_texts(room_id);
            CREATE INDEX IF NOT EXISTS idx_time_stats_room_type ON time_stats(room_id, stat_type);
            
            -- 房间订阅配置（持久化存储）
            CREATE TABLE IF NOT EXISTS room_subscriptions (
                uid INTEGER PRIMARY KEY,
                room_id INTEGER,
                uname TEXT,
                targets TEXT
            );
        """)
        await self._conn.commit()
    
    async def flush_buffer(self, buffer: StatsBuffer):
        """将缓冲数据批量写入数据库"""
        if self._conn is None:
            return
        
        async with self._conn.cursor() as cursor:
            # 房间统计
            for room_id, count in buffer.room_danmu_count.items():
                await cursor.execute("""
                    INSERT INTO room_stats (room_id, danmu_count) VALUES (?, ?)
                    ON CONFLICT(room_id) DO UPDATE SET danmu_count = danmu_count + excluded.danmu_count
                """, (room_id, count))
            
            for room_id, profit in buffer.room_gift_profit.items():
                await cursor.execute("""
                    INSERT INTO room_stats (room_id, gift_profit) VALUES (?, ?)
                    ON CONFLICT(room_id) DO UPDATE SET gift_profit = gift_profit + excluded.gift_profit
                """, (room_id, profit))
            
            for room_id, profit in buffer.room_sc_profit.items():
                await cursor.execute("""
                    INSERT INTO room_stats (room_id, sc_profit) VALUES (?, ?)
                    ON CONFLICT(room_id) DO UPDATE SET sc_profit = sc_profit + excluded.sc_profit
                """, (room_id, profit))
            
            for room_id, count in buffer.room_box_count.items():
                await cursor.execute("""
                    INSERT INTO room_stats (room_id, box_count) VALUES (?, ?)
                    ON CONFLICT(room_id) DO UPDATE SET box_count = box_count + excluded.box_count
                """, (room_id, count))
            
            for room_id, profit in buffer.room_box_profit.items():
                await cursor.execute("""
                    INSERT INTO room_stats (room_id, box_profit) VALUES (?, ?)
                    ON CONFLICT(room_id) DO UPDATE SET box_profit = box_profit + excluded.box_profit
                """, (room_id, profit))
            
            # 大航海统计
            for room_id, guards in buffer.room_guard_count.items():
                for guard_type, count in guards.items():
                    col = f"{guard_type.lower()}_count"
                    await cursor.execute(f"""
                        INSERT INTO room_stats (room_id, {col}) VALUES (?, ?)
                        ON CONFLICT(room_id) DO UPDATE SET {col} = {col} + excluded.{col}
                    """, (room_id, count))
            
            # 用户统计
            for (room_id, uid), count in buffer.user_danmu_count.items():
                await cursor.execute("""
                    INSERT INTO user_danmu (room_id, uid, count) VALUES (?, ?, ?)
                    ON CONFLICT(room_id, uid) DO UPDATE SET count = count + excluded.count
                """, (room_id, uid, count))
            
            for (room_id, uid), profit in buffer.user_gift_profit.items():
                await cursor.execute("""
                    INSERT INTO user_gift (room_id, uid, profit) VALUES (?, ?, ?)
                    ON CONFLICT(room_id, uid) DO UPDATE SET profit = profit + excluded.profit
                """, (room_id, uid, profit))
            
            for (room_id, uid), profit in buffer.user_sc_profit.items():
                await cursor.execute("""
                    INSERT INTO user_sc (room_id, uid, profit) VALUES (?, ?, ?)
                    ON CONFLICT(room_id, uid) DO UPDATE SET profit = profit + excluded.profit
                """, (room_id, uid, profit))
            
            for (room_id, uid), count in buffer.user_box_count.items():
                profit = buffer.user_box_profit.get((room_id, uid), 0)
                await cursor.execute("""
                    INSERT INTO user_box (room_id, uid, count, profit) VALUES (?, ?, ?, ?)
                    ON CONFLICT(room_id, uid) DO UPDATE SET 
                        count = count + excluded.count,
                        profit = profit + excluded.profit
                """, (room_id, uid, count, profit))
            
            for (room_id, uid, guard_type), months in buffer.user_guard_count.items():
                await cursor.execute("""
                    INSERT INTO user_guard (room_id, uid, guard_type, months) VALUES (?, ?, ?, ?)
                    ON CONFLICT(room_id, uid, guard_type) DO UPDATE SET months = months + excluded.months
                """, (room_id, uid, guard_type, months))
            
            # 弹幕文本
            now = int(time.time())
            for room_id, texts in buffer.room_danmu_texts.items():
                await cursor.executemany(
                    "INSERT INTO danmu_texts (room_id, content, timestamp) VALUES (?, ?, ?)",
                    [(room_id, text, now) for text in texts]
                )
            
            # 时间分布数据
            for room_id, times in buffer.room_danmu_times.items():
                await cursor.executemany(
                    "INSERT INTO time_stats (room_id, stat_type, timestamp, value) VALUES (?, 'danmu', ?, ?)",
                    [(room_id, t, v) for t, v in times]
                )
            
            for room_id, times in buffer.room_gift_times.items():
                await cursor.executemany(
                    "INSERT INTO time_stats (room_id, stat_type, timestamp, value) VALUES (?, 'gift', ?, ?)",
                    [(room_id, t, v) for t, v in times]
                )
            
            for room_id, times in buffer.room_sc_times.items():
                await cursor.executemany(
                    "INSERT INTO time_stats (room_id, stat_type, timestamp, value) VALUES (?, 'sc', ?, ?)",
                    [(room_id, t, v) for t, v in times]
                )
            
            for room_id, times in buffer.room_box_times.items():
                await cursor.executemany(
                    "INSERT INTO time_stats (room_id, stat_type, timestamp, value) VALUES (?, 'box', ?, ?)",
                    [(room_id, t, v) for t, v in times]
                )
            
            for room_id, times in buffer.room_guard_times.items():
                await cursor.executemany(
                    "INSERT INTO time_stats (room_id, stat_type, timestamp, value) VALUES (?, 'guard', ?, ?)",
                    [(room_id, t, v) for t, v in times]
                )
            
            # 盲盒盈亏记录
            for room_id, records in buffer.room_box_profit_records.items():
                await cursor.executemany(
                    "INSERT INTO box_profit_records (room_id, profit) VALUES (?, ?)",
                    [(room_id, p) for p in records]
                )
        
        await self._conn.commit()
    
    # ===== 直播状态管理 =====
    
    async def get_live_status(self, room_id: int) -> int:
        """获取直播状态 (0=未开播, 1=直播中, 2=轮播)"""
        async with self._conn.execute(
            "SELECT status FROM live_status WHERE room_id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def set_live_status(self, room_id: int, status: int):
        """设置直播状态"""
        await self._conn.execute("""
            INSERT INTO live_status (room_id, status) VALUES (?, ?)
            ON CONFLICT(room_id) DO UPDATE SET status = excluded.status
        """, (room_id, status))
        await self._conn.commit()
    
    async def set_live_start_time(self, room_id: int, start_time: int):
        """设置直播开始时间"""
        await self._conn.execute("""
            INSERT INTO live_status (room_id, start_time) VALUES (?, ?)
            ON CONFLICT(room_id) DO UPDATE SET start_time = excluded.start_time
        """, (room_id, start_time))
        await self._conn.commit()
    
    async def get_live_start_time(self, room_id: int) -> int:
        """获取直播开始时间"""
        async with self._conn.execute(
            "SELECT start_time FROM live_status WHERE room_id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def set_live_end_time(self, room_id: int, end_time: int):
        """设置直播结束时间"""
        await self._conn.execute("""
            INSERT INTO live_status (room_id, end_time) VALUES (?, ?)
            ON CONFLICT(room_id) DO UPDATE SET end_time = excluded.end_time
        """, (room_id, end_time))
        await self._conn.commit()
    
    async def get_live_end_time(self, room_id: int) -> int:
        """获取直播结束时间"""
        async with self._conn.execute(
            "SELECT end_time FROM live_status WHERE room_id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    # ===== 统计数据读取 =====
    
    async def get_room_stats(self, room_id: int) -> Dict[str, Any]:
        """获取房间统计数据"""
        # 先刷新缓冲
        await self.buffer.flush()
        
        async with self._conn.execute(
            "SELECT * FROM room_stats WHERE room_id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {
                    "danmu_count": 0,
                    "gift_profit": 0.0,
                    "sc_profit": 0,
                    "box_count": 0,
                    "box_profit": 0.0,
                    "captain_count": 0,
                    "commander_count": 0,
                    "governor_count": 0,
                }
            return {
                "danmu_count": row[1],
                "gift_profit": row[2],
                "sc_profit": row[3],
                "box_count": row[4],
                "box_profit": row[5],
                "captain_count": row[6],
                "commander_count": row[7],
                "governor_count": row[8],
            }
    
    async def get_user_danmu_ranking(self, room_id: int, limit: int = 10) -> List[Tuple[int, int]]:
        """获取用户弹幕排行"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT uid, count FROM user_danmu WHERE room_id = ? ORDER BY count DESC LIMIT ?",
            (room_id, limit)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_user_gift_ranking(self, room_id: int, limit: int = 10) -> List[Tuple[int, float]]:
        """获取用户礼物排行"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT uid, profit FROM user_gift WHERE room_id = ? ORDER BY profit DESC LIMIT ?",
            (room_id, limit)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_user_sc_ranking(self, room_id: int, limit: int = 10) -> List[Tuple[int, int]]:
        """获取用户SC排行"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT uid, profit FROM user_sc WHERE room_id = ? ORDER BY profit DESC LIMIT ?",
            (room_id, limit)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_user_box_ranking(self, room_id: int, limit: int = 10) -> List[Tuple[int, int]]:
        """获取用户盲盒数量排行"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT uid, count FROM user_box WHERE room_id = ? ORDER BY count DESC LIMIT ?",
            (room_id, limit)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_user_box_profit_ranking(self, room_id: int, limit: int = 10) -> List[Tuple[int, float]]:
        """获取用户盲盒盈亏排行"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT uid, profit FROM user_box WHERE room_id = ? ORDER BY profit DESC LIMIT ?",
            (room_id, limit)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_user_guard_list(self, room_id: int, guard_type: str) -> List[Tuple[int, int]]:
        """获取大航海列表"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT uid, months FROM user_guard WHERE room_id = ? AND guard_type = ? ORDER BY months DESC",
            (room_id, guard_type)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_danmu_texts(self, room_id: int) -> List[str]:
        """获取弹幕文本（用于词云）"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT content FROM danmu_texts WHERE room_id = ?", (room_id,)
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]
    
    async def get_time_stats(self, room_id: int, stat_type: str) -> List[Tuple[int, float]]:
        """获取时间分布数据"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT timestamp, value FROM time_stats WHERE room_id = ? AND stat_type = ? ORDER BY timestamp",
            (room_id, stat_type)
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]
    
    async def get_box_profit_records(self, room_id: int) -> List[float]:
        """获取盲盒盈亏记录"""
        await self.buffer.flush()
        async with self._conn.execute(
            "SELECT profit FROM box_profit_records WHERE room_id = ? ORDER BY id",
            (room_id,)
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]
    
    async def get_user_count(self, room_id: int, table: str) -> int:
        """获取发送人数"""
        await self.buffer.flush()
        async with self._conn.execute(
            f"SELECT COUNT(DISTINCT uid) FROM {table} WHERE room_id = ?", (room_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    # ===== 数据重置 =====
    
    async def reset_room_stats(self, room_id: int):
        """重置房间统计（开播时调用）"""
        tables = [
            "room_stats", "user_danmu", "user_gift", "user_sc",
            "user_box", "user_guard", "danmu_texts", "time_stats",
            "box_profit_records"
        ]
        for table in tables:
            await self._conn.execute(f"DELETE FROM {table} WHERE room_id = ?", (room_id,))
        await self._conn.commit()
    
    # ===== 场次管理 =====
    
    async def create_session(
        self, room_id: int, start_time: int,
        fans_before: int = -1, fans_medal_before: int = -1, guard_before: int = -1
    ) -> int:
        """创建新的直播场次"""
        cursor = await self._conn.execute("""
            INSERT INTO live_sessions (room_id, start_time, fans_before, fans_medal_before, guard_before)
            VALUES (?, ?, ?, ?, ?)
        """, (room_id, start_time, fans_before, fans_medal_before, guard_before))
        await self._conn.commit()
        return cursor.lastrowid
    
    async def end_session(
        self, room_id: int, end_time: int,
        fans_after: int = -1, fans_medal_after: int = -1, guard_after: int = -1
    ):
        """结束直播场次"""
        await self._conn.execute("""
            UPDATE live_sessions SET end_time = ?, fans_after = ?, fans_medal_after = ?, guard_after = ?
            WHERE room_id = ? AND end_time = 0
        """, (end_time, fans_after, fans_medal_after, guard_after, room_id))
        await self._conn.commit()
