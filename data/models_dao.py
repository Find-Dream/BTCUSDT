"""模型库数据访问（model_1m）。

15 码列名见 model.fingerprint.FIELDS。去重键 = 15 码。
model_type：1=开多 2=平多 3=开空 4=平空
"""
import time

from data import db
from model.fingerprint import FIELDS


def _cols():
    return ",".join(FIELDS)


def _placeholders(n):
    return ",".join(["?"] * n)


def insert_model(table, model_type, codes, uptime=None):
    """插入一条模型（codes 为 15 码列表）。"""
    if uptime is None:
        uptime = time.time()
    sql = "INSERT INTO %s (type,%s,uptime) VALUES (?,%s,?)" % (
        table, _cols(), _placeholders(15))
    return db.execute(sql, (model_type, *codes, uptime))


def match(table, codes, n=9):
    """按前 n 码精确匹配（n=9 -> 3 分钟；n=15 -> 5 分钟）。返回首条命中或 None。"""
    fields = FIELDS[:n]
    where = " AND ".join("%s = ?" % f for f in fields)
    rows = db.query(
        "SELECT * FROM %s WHERE %s LIMIT 1" % (table, where), tuple(codes[:n]))
    return rows[0] if rows else None


def all_code_keys(table):
    """取库中所有模型的 15 码元组集合，供去重。"""
    rows = db.query("SELECT %s FROM %s" % (_cols(), table))
    return set(tuple(r) for r in rows)


def exists(table, codes):
    """15 码是否已存在。"""
    return tuple(codes) in all_code_keys(table)


def list_models(table, limit=200):
    """列出模型（最新在前），供 Web 模型管理页。"""
    return db.query(
        "SELECT id,type,%s,uptime FROM %s ORDER BY id DESC LIMIT ?" % (_cols(), table),
        (limit,))


def delete_model(table, model_id):
    db.execute("DELETE FROM %s WHERE id = ?" % table, (model_id,))


def get_by_id(table, model_id):
    rows = db.query("SELECT * FROM %s WHERE id = ?" % table, (model_id,))
    return rows[0] if rows else None
