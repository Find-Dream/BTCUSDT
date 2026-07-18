"""SQLite 数据库层（替换 MySQL）。

数据库文件路径由 config.yaml → paths.db_path 指定，默认 data/btcusdt.db。
SQLite 是 Python 内置模块，无需额外安装依赖。

并发策略：
  - 每个线程独享一个 SQLite 连接（thread-local）
  - WAL 日志模式：允许多读一写，适合交易 + Web 双线程并发
  - 写操作（execute）自动提交

DAO 文件无需改动——占位符 ? 与 SQLite 原生一致。
"""
import os
import sqlite3
import threading
import time

from bin import config

_local = threading.local()

# 15 码列定义，供 model_1m 复用
_FP_COLS = (
    "spot_1 INTEGER, m5_1 INTEGER, m3_1 INTEGER, "
    "spot_2 INTEGER, m5_2 INTEGER, m3_2 INTEGER, "
    "spot_3 INTEGER, m5_3 INTEGER, m3_3 INTEGER, "
    "spot_4 INTEGER, m5_4 INTEGER, m3_4 INTEGER, "
    "spot_5 INTEGER, m5_5 INTEGER, m3_5 INTEGER"
)

_SCHEMA = [
    # ── 模型库（只保留 1m；5m 已弃用）──
    "CREATE TABLE IF NOT EXISTS model_1m "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, type INTEGER, %s, uptime REAL)" % _FP_COLS,

    # ── 命中信号 ──
    "CREATE TABLE IF NOT EXISTS monitor_auto "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER, model_type INTEGER, "
    "last REAL, uptime REAL)",

    # ── 仓位 ──
    "CREATE TABLE IF NOT EXISTS pos "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, side TEXT, start_last REAL, "
    "last REAL, sz INTEGER, uptime REAL)",

    "CREATE TABLE IF NOT EXISTS pos_log "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, side TEXT, side_1 TEXT, "
    "last REAL, pos_last REAL, sz INTEGER, postype INTEGER, uptime REAL)",

    "CREATE TABLE IF NOT EXISTS pos_ok "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, pos INTEGER, uptime REAL)",

    # ── 宏观 / gap ──
    "CREATE TABLE IF NOT EXISTS situation "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, situation_24h_id INTEGER, "
    "situation_1h_id INTEGER, uptime REAL)",

    "CREATE TABLE IF NOT EXISTS last_gap "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, last REAL, gap REAL, uptime REAL)",

    "CREATE TABLE IF NOT EXISTS gap_rule_num "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, num INTEGER, uptime REAL)",
]

# 高频写入表的 WAL 友好索引
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_monitor_auto_uptime ON monitor_auto(uptime)",
    "CREATE INDEX IF NOT EXISTS idx_monitor_auto_type   ON monitor_auto(model_type, uptime)",
    "CREATE INDEX IF NOT EXISTS idx_pos_log_uptime       ON pos_log(uptime)",
    "CREATE INDEX IF NOT EXISTS idx_last_gap_uptime      ON last_gap(uptime)",
    "CREATE INDEX IF NOT EXISTS idx_situation_uptime     ON situation(uptime)",
]


def _db_file() -> str:
    """返回 SQLite 文件的绝对路径。"""
    cfg = config.get("paths") or {}
    rel = cfg.get("db_path", "data/btcusdt.db")
    if os.path.isabs(rel):
        return rel
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def get_conn() -> sqlite3.Connection:
    """线程内复用一个 SQLite 连接。首次调用时创建并配置 WAL 模式。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = _db_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = None   # 返回 tuple，与 DAO 期望一致
    _local.conn = conn
    return conn


def checkpoint():
    """WAL checkpoint，减少 WAL 文件膨胀。定期或退出前调用。"""
    try:
        get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass


def db_path() -> str:
    """返回数据库文件路径（供 main.py 打印）。"""
    return _db_file()


def query(sql: str, params=()):
    """SELECT，返回全部行（list of tuple）。"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    return list(cur.fetchall())


def execute(sql: str, params=()):
    """INSERT/UPDATE/DELETE，自动提交，返回 lastrowid。"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def init_db(seed: bool = True) -> str:
    """建表、建索引，可选写入初始行。"""
    conn = get_conn()
    for ddl in _SCHEMA:
        conn.execute(ddl)
    for idx in _INDEXES:
        conn.execute(idx)
    conn.commit()

    if seed:
        now = time.time()
        if not query("SELECT 1 FROM pos LIMIT 1"):
            execute("INSERT INTO pos VALUES (NULL,'long',0,0,0,?)",  (now,))
            execute("INSERT INTO pos VALUES (NULL,'short',0,0,0,?)", (now,))
        if not query("SELECT 1 FROM pos_ok LIMIT 1"):
            execute("INSERT INTO pos_ok VALUES (NULL,3,?)", (now,))
        if not query("SELECT 1 FROM gap_rule_num LIMIT 1"):
            execute("INSERT INTO gap_rule_num VALUES (NULL,0,?)", (now,))

    return db_path()


if __name__ == "__main__":
    print("初始化数据库:", init_db())
