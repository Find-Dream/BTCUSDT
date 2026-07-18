"""后台调度（两条循环：交易 + 形势）。

_study_loop 已移除——指纹不再采样入库，
实时匹配在 monitor 内存缓存中完成。
"""
import threading

from bin import config, kline, monitor, mark
from bin.logger import get_logger
from data import db

log = get_logger("scheduler")

_stop = threading.Event()
_threads = []


def _trade_loop():
    interval = config.get("runtime", "loop_interval", 1)
    while not _stop.is_set():
        try:
            jg = kline.fetch(bar="1m", save=False)
            if jg and len(jg) >= 25:
                monitor.run(jg, table="model_1m")
                mark.run(jg)
        except Exception as e:
            log.error("交易循环异常: %s", e)
        _stop.wait(interval)


def _situation_loop():
    interval = config.get("runtime", "situation_interval", 50)
    while not _stop.is_set():
        try:
            mark.get_situation()
            db.checkpoint()
        except Exception as e:
            log.error("形势循环异常: %s", e)
        _stop.wait(interval)


def start():
    """启动后台循环（幂等）。"""
    if _threads:
        return
    db.init_db()
    # 启动时预热内存缓存（只保留 model_1m）
    monitor.reload_cache("model_1m")
    log.info("调度启动：交易/形势 两循环，模型缓存已预热")
    for target in (_trade_loop, _situation_loop):
        t = threading.Thread(target=target, daemon=True)
        t.start()
        _threads.append(t)


def stop():
    _stop.set()
    log.info("调度停止")
