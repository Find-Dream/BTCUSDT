"""匹配引擎：实时指纹与已晋升模型在内存中比对，无 DB 写操作。

流程：K 线 -> 15 码指纹 -> 内存缓存前 9 码匹配 -> 时间窗去重 ->
      振幅门 + 形状门 -> 写 monitor_auto / monitor_log -> 触发后续动作。

模型缓存（_CACHE）在启动时或新模型晋升后通过 reload_cache() 刷新，
匹配过程纯内存运算，不产生额外 SQL 读请求。
"""
import threading
import time

from bin import config
from bin.logger import get_logger
from data import models_dao, signal_dao
from model.fingerprint import fingerprint, time_window

log = get_logger("monitor")

# ---- 内存模型缓存 ----
# 结构：{ table: [ (id, type, (code1..code15)), ... ] }
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


def reload_cache(table="model_1m"):
    """从 DB 全量加载指定表的模型到内存缓存，晋升新模型后调用。"""
    rows = models_dao.list_models(table, limit=10000)
    # rows: (id, type, c1..c15, uptime)  共 18 列
    entries = [(r[0], r[1], tuple(r[2:17])) for r in rows]
    with _CACHE_LOCK:
        _CACHE[table] = entries
    log.info("模型缓存已刷新 table=%s 共 %d 条", table, len(entries))


def _match(table, codes, n=9):
    """在内存缓存中按前 n 码匹配，返回 (id, type, codes_tuple) 或 None。"""
    target = tuple(codes[:n])
    with _CACHE_LOCK:
        models = _CACHE.get(table, [])
    for entry in models:
        if entry[2][:n] == target:
            return entry
    return None


def run(jg_list, table="model_1m"):
    """对一批 K 线做一次匹配。返回命中信号 dict 或 None。"""
    if len(jg_list) < 25:
        log.error("K 线不足，跳过匹配 len=%d", len(jg_list))
        return None

    # 缓存为空时懒加载（首次运行）
    with _CACHE_LOCK:
        cache_empty = table not in _CACHE
    if cache_empty:
        reload_cache(table)

    strat = config.get("strategy")
    band_10  = strat.get("ma_spot_band_10", 10)
    band_20  = strat.get("ma_spot_band_20", 20)
    line_band = strat.get("ma_line_band", 10)
    amp_open  = strat.get("amp_open", 10)
    amp_close = strat.get("amp_close", 20)

    open_money  = float(jg_list[0][1])
    close_money = float(jg_list[0][4])
    last = float(jg_list[0][4])
    now  = time.time()

    codes = fingerprint(jg_list, band_10, band_20, line_band)
    log.info("当前指纹 %s", codes)

    # ---- 前 9 码（3 分钟）内存匹配 ----
    hit = _match(table, codes, 9)
    if not hit:
        return None   # 无匹配直接丢弃，不写库
    model_id, model_type = hit[0], hit[1]
    log.info("命中模型 id=%s type=%s", model_id, model_type)

    # ---- 时间窗去重 ----
    start, end = time_window(jg_list)
    same_window = signal_dao.signal_in_window(start, end)
    if same_window and int(same_window[0][2]) == model_type:
        log.info("该时间窗已存在相同类型信号，跳过")
        return None

    # 窗内为空 或 类型不同 -> 继续判定振幅/形状
    if not same_window:
        passed = _gate(model_type, open_money, close_money, codes, amp_open, amp_close)
    else:
        passed = True   # 类型不同，直接记录

    if not passed:
        return None

    # ---- 记录信号（仍需写 DB，供图表标注与后续交易）----
    signal_dao.add_log("命中模型ID:%s 类型:%s" % (model_id, model_type), now)
    signal_dao.add_signal(model_id, model_type, last, now)
    log.info("写入信号 monitor_auto id=%s type=%s last=%s", model_id, model_type, last)

    return {"model_id": model_id, "model_type": model_type, "last": last, "uptime": now}


def _gate(model_type, open_money, close_money, codes, amp_open, amp_close):
    """振幅门 + 形状门。"""
    if model_type in (2, 4):
        if (model_type == 2 and open_money - close_money > amp_close) or \
           (model_type == 4 and close_money - open_money > amp_close):
            return True
        log.info("振幅不足平仓门 %.2f", abs(open_money - close_money))
        return False
    else:
        model_spot, model_line_5, model_line_10 = codes[0], codes[1], codes[2]
        shape_ok = (model_spot != 100 and model_line_5 == 600 and model_line_10 == 600) or \
                   (model_spot != 100 and model_line_5 == 500 and model_line_10 == 500)
        if not shape_ok:
            log.info("开仓形状门不匹配 spot=%s l5=%s l10=%s", model_spot, model_line_5, model_line_10)
            return False
        if (model_type == 3 and open_money - close_money > amp_open) or \
           (model_type == 1 and close_money - open_money > amp_open):
            return True
        log.info("振幅不足开仓门 %.2f", abs(open_money - close_money))
        return False
