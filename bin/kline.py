"""K 线抓取（不落库版）。

从 OKX 抓 K 线 -> 返回给调度引擎使用，不再写数据库。
所有历史范围查询也直接走 OKX，带短期内存缓存避免频繁请求。
"""
import time
import threading

from bin import config, okx_client
from bin.logger import get_logger

log = get_logger("kline")

OKX_PAGE   = 300                            # OKX 单次最大条数
BAR_SECONDS = {"1m": 60, "5m": 300, "15m": 900}

# ---------- 24h 高低价缓存（供 mark.py 开仓门限使用）----------
_HL_CACHE: dict = {}          # bar -> (cached_at, high, low)
_HL_LOCK = threading.Lock()
_HL_TTL  = 60                 # 缓存 60 秒


def fetch(bar=None, limit=None, save=False):
    """抓取指定周期 K 线，返回 OKX 原始 data 数组（newest-first）。

    save 参数保留以兼容旧调用，但不再落库。
    """
    rt = config.get("runtime")
    inst_id = rt.get("inst_id", "BTC-USDT-SWAP")
    if bar is None:
        bar = rt.get("bar", "1m")
    if limit is None:
        limit = rt.get("kline_limit", 30)

    data = okx_client.get_candles(inst_id, bar=bar, limit=limit)
    if not data:
        log.error("抓取 K 线为空 bar=%s", bar)
        return []
    log.info("抓取 K 线 bar=%s 根数=%d 最新价=%s", bar, len(data), data[0][4])
    return data


def fetch_range(bar, start_ts, end_ts):
    """直接从 OKX 拉取 [start_ts, end_ts] 范围的 K 线，不存库。

    返回 oldest-first 列表，每项为 OKX 原始数组：
        [ts_ms, open, high, low, close, vol, volCcy, ...]
    """
    rt = config.get("runtime")
    inst_id = rt.get("inst_id", "BTC-USDT-SWAP")
    bar_sec  = BAR_SECONDS.get(bar, 60)
    start_ms = start_ts * 1000
    end_ms   = end_ts   * 1000

    all_data = []
    after_ms = end_ms + bar_sec * 1000

    while True:
        data = okx_client.get_history_candles(inst_id, bar=bar, limit=OKX_PAGE, after=after_ms)
        if not data:
            data = okx_client.get_candles(inst_id, bar=bar, limit=OKX_PAGE, after=after_ms)
        if not data:
            break
        relevant = [d for d in data if start_ms <= int(d[0]) <= end_ms]
        all_data.extend(relevant)
        if int(data[-1][0]) <= start_ms:
            break
        after_ms = int(data[-1][0])
        time.sleep(0.1)

    seen = {}
    for d in all_data:
        seen[int(d[0])] = d
    result = sorted(seen.values(), key=lambda x: int(x[0]))
    log.info("fetch_range bar=%s 共 %d 根", bar, len(result))
    return result


def day_high_low(bar="1m", seconds=43200):
    """从 OKX 获取最近 seconds 秒（默认12h）的最高价与最低价。

    结果缓存 60 秒，避免交易循环每秒都发起 API 请求。
    失败时返回 (None, None)，调用方应降级处理。
    """
    now = time.time()
    with _HL_LOCK:
        cached = _HL_CACHE.get(bar)
        if cached and now - cached[0] < _HL_TTL:
            return cached[1], cached[2]

    raw = fetch_range(bar, int(now) - seconds, int(now))
    if not raw:
        return None, None

    high = max(float(r[2]) for r in raw)   # OKX r[2] = high
    low  = min(float(r[3]) for r in raw)   # OKX r[3] = low

    with _HL_LOCK:
        _HL_CACHE[bar] = (now, high, low)
    log.info("day_high_low bar=%s high=%.2f low=%.2f (缓存60s)", bar, high, low)
    return high, low
