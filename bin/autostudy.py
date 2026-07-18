"""手动晋升：把指定时间点的指纹写入模型库。

原采样（sample_study）与自动学习（monitor_autostudy）已移除——
指纹只在用户点击晋升按钮时现算现入库，实时匹配在内存缓存中完成，
不再对 model_study 做任何写入。
"""
from bin.logger import get_logger
from data import models_dao

log = get_logger("autostudy")


def promote(codes, model_type, table="model_1m"):
    """手动晋升（供 Web 晋升按钮），去重后写入模型库。返回新 id 或 None（已存在）。"""
    if models_dao.exists(table, codes):
        return None
    mid = models_dao.insert_model(table, model_type, codes)
    log.info("手动晋升模型 id=%s type=%s table=%s", mid, model_type, table)
    return mid
