"""信号 / 宏观 / gap 数据访问（monitor_auto、monitor_log、situation、last_gap、gap_rule_num）。"""
import time

from data import db


# ---------------- monitor_auto：命中信号 ----------------
def add_signal(model_id, model_type, last, uptime=None):
    if uptime is None:
        uptime = time.time()
    return db.execute("INSERT INTO monitor_auto VALUES (Null,?,?,?,?)",
                      (model_id, model_type, last, uptime))


def select_signal(model_type, since):
    """查询 since 之后是否有指定类型的新信号。"""
    return db.query(
        "SELECT * FROM monitor_auto WHERE model_type = ? AND uptime > ? ORDER BY id DESC LIMIT 1",
        (model_type, since))


def signal_in_window(start, end):
    """时间窗内已存在的信号（去重用）。"""
    return db.query(
        "SELECT * FROM monitor_auto WHERE uptime >= ? AND uptime <= ?", (start, end))


def list_signals(limit=200):
    return db.query("SELECT * FROM monitor_auto ORDER BY id DESC LIMIT ?", (limit,))


# ---------------- monitor_log ----------------
def add_log(text, uptime=None):
    if uptime is None:
        uptime = time.time()
    return db.execute("INSERT INTO monitor_log VALUES (Null,?,?)", (text, uptime))


# ---------------- situation：宏观形势缓存 ----------------
def latest_situation():
    rows = db.query("SELECT * FROM situation ORDER BY uptime DESC LIMIT 1")
    return rows[0] if rows else None


def add_situation(s24, s1, uptime=None):
    if uptime is None:
        uptime = time.time()
    db.execute("INSERT INTO situation VALUES (Null,?,?,?)", (s24, s1, uptime))


def avg_last(seconds):
    """last_gap 表在最近 seconds 秒内的 last 均价。"""
    since = time.time() - seconds
    rows = db.query("SELECT AVG(last) FROM last_gap WHERE uptime > ?", (since,))
    return rows[0][0] if rows and rows[0][0] is not None else None


# ---------------- last_gap：tick 价差 ----------------
def add_gap(last):
    """写入一条 last_gap，返回本次 gap = last - 上一 last。"""
    rows = db.query("SELECT last FROM last_gap ORDER BY id DESC LIMIT 1")
    if not rows:
        gap = 0
    else:
        gap = float(last) - float(rows[0][0])
    db.execute("INSERT INTO last_gap VALUES (Null,?,?,?)", (last, gap, time.time()))
    return gap


def last_n_gaps(n=10):
    """最近 n 个 gap（newest-first）。"""
    rows = db.query("SELECT gap FROM last_gap ORDER BY id DESC LIMIT ?", (n,))
    return [r[0] for r in rows]


def latest_last():
    rows = db.query("SELECT last FROM last_gap ORDER BY id DESC LIMIT 1")
    return float(rows[0][0]) if rows else None


# ---------------- gap_rule_num：暴涨暴跌状态 ----------------
def get_gap_rule_num():
    rows = db.query("SELECT num FROM gap_rule_num ORDER BY id DESC LIMIT 1")
    return rows[0][0] if rows else 0


def set_gap_rule_num(num):
    db.execute("INSERT INTO gap_rule_num VALUES (Null,?,?)", (num, time.time()))
