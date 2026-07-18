"""K 线数据访问（api_k_1m / api_k_5m / api_k_15m）。"""
import time

from data import db

_TABLES = {"1m": "api_k_1m", "5m": "api_k_5m", "15m": "api_k_15m"}


def _table(bar):
    if bar not in _TABLES:
        raise ValueError("不支持的周期: %s" % bar)
    return _TABLES[bar]


def upsert(bar, row):
    """按 ts 落库一根 K 线。row = [ts_ms, open, high, low, close, vol, volCcy, ...]。

    ts 存秒（对齐老项目 int(ts_ms)/1000）。已存在则更新，否则插入。
    """
    table = _table(bar)
    ts = int(int(row[0]) / 1000)
    open_, high, low, close = float(row[1]), float(row[2]), float(row[3]), float(row[4])
    vol = float(row[5]) if len(row) > 5 else 0
    vol_ccy = float(row[6]) if len(row) > 6 else 0
    now = time.time()
    exist = db.query("SELECT id FROM %s WHERE ts = ?" % table, (ts,))
    if exist:
        db.execute(
            "UPDATE %s SET open=?,hight=?,low=?,close=?,vol=?,vol_ccy=?,uptime=? WHERE ts=?" % table,
            (open_, high, low, close, vol, vol_ccy, now, ts),
        )
    else:
        db.execute(
            "INSERT INTO %s VALUES (Null,?,?,?,?,?,?,?,?)" % table,
            (open_, high, low, close, ts, vol, vol_ccy, now),
        )


def save_batch(bar, rows):
    """批量落库（rows 为 OKX candles data，newest-first）。"""
    for row in rows:
        upsert(bar, row)


def latest(bar, limit=200):
    """取最近 limit 根 K 线，返回 newest-first 的行列表。"""
    table = _table(bar)
    return db.query(
        "SELECT id,open,hight,low,close,ts,vol,vol_ccy,uptime FROM %s ORDER BY ts DESC LIMIT ?" % table,
        (limit,),
    )


def day_high_low(bar="1m", seconds=43200):
    """最近 seconds 秒（默认 12h/43200）的最高价与最低价，用于 24h 区间闸门。"""
    table = _table(bar)
    since = time.time() - seconds
    row = db.query(
        "SELECT MAX(hight), MIN(low) FROM %s WHERE uptime > ?" % table, (since,)
    )
    if row and row[0][0] is not None:
        return row[0][0], row[0][1]
    return None, None


def window_until(bar, ts, limit=30):
    """取截至某根 K 线（ts 为该根的秒级时间戳）为止的最近 limit 根，newest-first。

    用于「按指定时间点计算指纹」——晋升历史某一时刻的图形。
    ts 存储为秒。返回行同 latest()：id,open,hight,low,close,ts,vol,vol_ccy,uptime。
    """
    table = _table(bar)
    return db.query(
        "SELECT id,open,hight,low,close,ts,vol,vol_ccy,uptime FROM %s "
        "WHERE ts <= ? ORDER BY ts DESC LIMIT ?" % table,
        (int(ts), limit),
    )


def since(bar, seconds=86400):
    """取最近 seconds 秒内的所有 K 线（newest-first），用于图表展示。

    按时间范围查询，中间断档的位置自然缺失，不会用更早的数据凑数。
    """
    table = _table(bar)
    cutoff = int(time.time()) - seconds
    return db.query(
        "SELECT id,open,hight,low,close,ts,vol,vol_ccy,uptime "
        "FROM %s WHERE ts >= ? ORDER BY ts DESC" % table,
        (cutoff,),
    )


def count_since(bar, seconds=86400):
    """统计最近 seconds 秒内实际有多少根 K 线（用于断档检测）。"""
    table = _table(bar)
    cutoff = int(time.time()) - seconds
    rows = db.query("SELECT COUNT(*) FROM %s WHERE ts >= ?" % table, (cutoff,))
    return rows[0][0] if rows else 0


def oldest_ts_since(bar, seconds=86400):
    """最近 seconds 秒窗口内最早一根的时间戳，不存在则 None。"""
    table = _table(bar)
    cutoff = int(time.time()) - seconds
    rows = db.query("SELECT MIN(ts) FROM %s WHERE ts >= ?" % table, (cutoff,))
    return rows[0][0] if rows and rows[0][0] is not None else None


    """返回当前周期在 DB 中的 K 线总条数。"""
    table = _table(bar)
    rows = db.query("SELECT COUNT(*) FROM %s" % table)
    return rows[0][0] if rows else 0


def oldest_ts(bar):
    """返回最早一根 K 线的秒级时间戳，不存在时返回 None。"""
    table = _table(bar)
    rows = db.query("SELECT MIN(ts) FROM %s" % table)
    return rows[0][0] if rows and rows[0][0] is not None else None


def to_model_rows(rows):
    """把 DB 行转成模型计算所需格式 [ts_ms, open, high, low, close, vol, vol_ccy]。

    DB 行：(id, open, hight, low, close, ts_sec, vol, vol_ccy, uptime)
    模型函数只用 close(i[4]) 与 ts(i[0])，此处补齐字段顺序。
    """
    out = []
    for r in rows:
        # r[5]=ts_sec -> 毫秒
        out.append([int(r[5]) * 1000, r[1], r[2], r[3], r[4], r[6], r[7]])
    return out
