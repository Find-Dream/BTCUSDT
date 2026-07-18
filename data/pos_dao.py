"""仓位数据访问（pos / pos_log / pos_ok / pos_rule）。"""
import time

from data import db


# ---------------- pos：当前持仓 ----------------
def get_pos(side):
    """返回某方向持仓行 (id, side, start_last, last, sz, uptime)，不存在则 None。"""
    rows = db.query("SELECT * FROM pos WHERE side = ? ORDER BY id DESC LIMIT 1", (side,))
    return rows[0] if rows else None


def set_pos(side, last, sz, uptime=None):
    """更新持仓均价与数量（不改 start_last）。"""
    if uptime is None:
        uptime = time.time()
    db.execute("UPDATE pos SET last=?, sz=?, uptime=? WHERE side=?", (last, sz, uptime, side))


def set_pos_start(side, start_last, sz, uptime=None):
    """开/平仓：同时设置 start_last 与 last。"""
    if uptime is None:
        uptime = time.time()
    db.execute("UPDATE pos SET start_last=?, last=?, sz=?, uptime=? WHERE side=?",
               (start_last, start_last, sz, uptime, side))


# ---------------- pos_log：订单流水 ----------------
def add_pos_log(side, side_1, last, pos_last, sz, postype, uptime=None):
    """追加一条订单流水，返回 id。side_1: buy/sell。"""
    if uptime is None:
        uptime = time.time()
    return db.execute(
        "INSERT INTO pos_log VALUES (Null,?,?,?,?,?,?,?)",
        (side, side_1, last, pos_last, sz, postype, uptime))


def latest_pos_log():
    rows = db.query("SELECT * FROM pos_log ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None


def list_pos_log(since=None, limit=500):
    if since is not None:
        return db.query(
            "SELECT * FROM pos_log WHERE uptime > ? ORDER BY id DESC LIMIT ?", (since, limit))
    return db.query("SELECT * FROM pos_log ORDER BY id DESC LIMIT ?", (limit,))


# ---------------- pos_ok：方向许可 ----------------
def get_pos_ok():
    """0=禁止 1=只多 2=只空 3=多空皆可。"""
    rows = db.query("SELECT pos FROM pos_ok ORDER BY id DESC LIMIT 1")
    return rows[0][0] if rows else 3


def set_pos_ok(value, uptime=None):
    if uptime is None:
        uptime = time.time()
    db.execute("INSERT INTO pos_ok VALUES (Null,?,?)", (value, uptime))
