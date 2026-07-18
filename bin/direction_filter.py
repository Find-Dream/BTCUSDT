"""开多/开空方向过滤模块。

在开仓或加仓前调用，通过多维度评分判断是否符合交易方向。

维度及满分：
  1. 趋势（EMA5/20/60 排列 + MACD 柱斜率）   ：±3
  2. 成交量（量价关系 + 突破有效性 + 量价背离）：±5
  3. 微观结构（OBI + 主动买入比，实盘可选）   ：±3
  4. 市场情绪（资金费率 + 多空比，实盘可选）  ：±3
  总分范围 [-14, +14]

判断阈值（config.yaml direction_filter.threshold，默认 6）：
  score >= +threshold  → 允许开多
  score <= -threshold  → 允许开空
  否则 → 拒绝，跳过本次下单

用法（实盘）：
  allowed, score, detail = check_direction("long")

用法（回测，传入 oldest-first candles）：
  allowed, score, detail = check_direction("long", candles=data[max(0,i-79):i+1])
"""
import time
import threading

from bin import config, okx_client
from bin.logger import get_logger

log = get_logger("direction_filter")

# ── 实盘 K 线缓存（避免每次下单都拉接口）──
_CANDLE_CACHE: dict = {}   # bar → (cached_at, candles_oldest_first)
_CACHE_LOCK = threading.Lock()
_CACHE_TTL  = 30           # 缓存 30 秒


# ──────────────────── 工具函数 ────────────────────

def _ema(prices: list, n: int) -> list:
    """计算 EMA 序列（oldest-first）。长度不足时以首价起步（等效 SMA 热身）。"""
    if not prices:
        return []
    alpha = 2.0 / (n + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(result[-1] * (1 - alpha) + p * alpha)
    return result


def _linear_slope_sign(values: list) -> int:
    """线性回归斜率符号：+1 上升，-1 下降，0 持平。"""
    n = len(values)
    if n < 2:
        return 0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num   = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom == 0:
        return 0
    slope = num / denom
    if slope > 1e-12:
        return 1
    if slope < -1e-12:
        return -1
    return 0


# ──────────────────── 各维度评分 ────────────────────

def score_trend(closes: list) -> int:
    """趋势维度评分（上限 ±3）。

    EMA5/20/60 多头/空头排列 ±2，MACD 柱方向 ±1。
    candles 不足时各子项跳过，不强制需要 60 根。
    """
    score = 0
    n = len(closes)
    if n < 5:
        return 0

    e5  = _ema(closes, 5)
    e20 = _ema(closes, min(20, n))
    e60 = _ema(closes, min(60, n))
    last_e5, last_e20, last_e60 = e5[-1], e20[-1], e60[-1]

    if last_e5 > last_e20 > last_e60:
        score += 2   # 多头排列
    elif last_e5 < last_e20 < last_e60:
        score -= 2   # 空头排列

    # MACD（12/26/9）柱斜率：至少需要 27 根（26 + 1 信号线热身）
    if n >= 27:
        macd_line = [m - s for m, s in zip(_ema(closes, 12), _ema(closes, 26))]
        signal    = _ema(macd_line, 9)
        # macd_line 与 signal 等长（都是 n 长），直接对齐
        histo     = [m - s for m, s in zip(macd_line, signal)]
        if len(histo) >= 3:
            recent_h  = histo[-min(5, len(histo)):]
            slope_sig = _linear_slope_sign(recent_h)
            last_h    = histo[-1]
            if last_h > 0 and slope_sig > 0:
                score += 1   # 柱正且向上
            elif last_h < 0 and slope_sig < 0:
                score -= 1   # 柱负且向下

    return max(-3, min(3, score))


def _vol_ratio(vols: list, window: int) -> float:
    """当前成交量相对近 window 根均量的倍数。"""
    avg = sum(vols[-(window + 1):-1]) / window
    return vols[-1] / avg if avg > 0 else 1.0


def _score_price_volume(closes: list, vols: list,
                        vr: float,
                        price_threshold: float,
                        vol_high: float) -> tuple:
    """量价关系评分（±2）。

    返回 (score, vol_high_ok)；vol_high_ok 供突破有效性子函数复用，
    避免重复计算。

      +2：价涨量增（趋势延续信号）
      -2：价跌量增（下跌动能充足）
       0：价量不匹配或变动幅度不足（方向不明）
    """
    dp         = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] != 0 else 0
    price_up   = dp >  price_threshold
    price_down = dp < -price_threshold
    vol_high_ok = vr > vol_high

    if price_up and vol_high_ok:
        return 2, vol_high_ok    # 价涨量增
    if price_down and vol_high_ok:
        return -2, vol_high_ok   # 价跌量增
    return 0, vol_high_ok        # 量不足或价格波动过小，方向不明


def _score_breakout(closes: list, highs: list, lows: list,
                    window: int, vol_high_ok: bool) -> int:
    """突破有效性评分（±3）。

    以近 window 根的最高/最低价为参考：
      +3：放量上方突破（有效突破）
      -1：缩量上方突破（假突破警告）
      -3：放量下方跌破（有效跌破）
      +1：缩量下方跌破（假跌破，可能反弹）
       0：价格仍在区间内
    """
    win    = min(window, len(closes) - 1)
    r_high = max(highs[-(win + 1):-1])
    r_low  = min(lows[-(win + 1):-1])
    cur    = closes[-1]

    if cur > r_high:
        return 3 if vol_high_ok else -1
    if cur < r_low:
        return -3 if vol_high_ok else 1
    return 0


def _score_divergence(closes: list, vols: list, window: int) -> int:
    """量价背离评分（±2）。

    对过去 window 根 K 线分别做价格和成交量的线性斜率判断：
      +2：量价齐升（价↑量↑），趋势最健康
      -2：量价齐跌（价↓量↓），动能最弱
      -1：涨势缩量（价↑量↓），动能衰减，小幅警惕
       0：跌势放量（价↓量↑），含义模糊，不给分
    """
    dw = min(window, len(closes))
    if dw < 5:
        return 0

    ps = _linear_slope_sign(closes[-dw:])
    vs = _linear_slope_sign(vols[-dw:])

    if ps > 0 and vs > 0:
        return 2    # 量价齐升
    if ps < 0 and vs < 0:
        return -2   # 量价齐跌
    if ps > 0 and vs < 0:
        return -1   # 涨势缩量，动能衰减
    # ps < 0 and vs > 0：跌势放量，含义模糊
    return 0


def score_volume(candles: list,
                 vol_window:      int   = 20,
                 breakout_window: int   = 20,
                 diverge_window:  int   = 20,
                 price_threshold: float = 0.001,
                 vol_high:        float = 1.5,
                 vol_low:         float = 0.8) -> int:
    """成交量维度综合评分，截断至 ±5。

    子维度：
      量价关系   ±2 — 当前 K 线价格涨跌方向与成交量放缩是否匹配
      突破有效性 ±3 — 近期高低点突破/跌破是否有成交量支撑
      量价背离   ±2 — 过去 N 根价格趋势与成交量趋势是否背离

    OKX candle 格式：[ts_ms, open, high, low, close, vol, ...]
    """
    if len(candles) < vol_window + 2:
        return 0

    closes = [float(c[4]) for c in candles]
    highs  = [float(c[2]) for c in candles]
    lows   = [float(c[3]) for c in candles]
    vols   = [float(c[5]) for c in candles]

    vr                  = _vol_ratio(vols, vol_window)
    s_pv, vol_high_ok   = _score_price_volume(closes, vols, vr, price_threshold, vol_high)
    s_bo                = _score_breakout(closes, highs, lows, breakout_window, vol_high_ok)
    s_div               = _score_divergence(closes, vols, diverge_window)

    return max(-5, min(5, s_pv + s_bo + s_div))


def score_microstructure(obi: float = None,
                         aggressive_buy_ratio: float = None) -> int:
    """微观结构维度评分（上限 ±3）。

    obi: 订单簿不平衡度 (bid_vol - ask_vol) / (bid_vol + ask_vol)，范围 [-1, 1]
    aggressive_buy_ratio: 主动买入占比，范围 [0, 1]
    两者均为 None 时返回 0（回测场景）。
    """
    score = 0
    if obi is not None:
        if obi > 0.3:
            score += 2   # 买方挂单明显更多
        elif obi < -0.3:
            score -= 2   # 卖方挂单明显更多
    if aggressive_buy_ratio is not None:
        if aggressive_buy_ratio > 0.6:
            score += 1
        elif aggressive_buy_ratio < 0.4:
            score -= 1
    return max(-3, min(3, score))


def score_sentiment(funding_rate: float = None,
                    long_short_ratio: float = None) -> int:
    """市场情绪维度评分（上限 ±3）。注意：情绪是逆向信号。

    funding_rate: 资金费率原始值，如 0.001 = 0.1%
    long_short_ratio: 多空账户比（多头账户数 / 空头账户数）
    两者均为 None 时返回 0（回测场景）。
    """
    score = 0
    if funding_rate is not None:
        fr_pct = funding_rate * 100
        if fr_pct < -0.05:
            score += 2   # 空头过热，逆向看多
        elif fr_pct > 0.1:
            score -= 2   # 多头过热，逆向看空
    if long_short_ratio is not None:
        if long_short_ratio < 0.8:
            score += 1   # 空头占主导，逆向看多
        elif long_short_ratio > 1.5:
            score -= 1   # 多头占主导，逆向看空
    return max(-3, min(3, score))


# ──────────────────── 实盘 K 线抓取缓存 ────────────────────

def _fetch_candles_cached(limit: int = 80) -> list:
    """抓取最近 K 线（oldest-first），带 30 秒内存缓存。仅实盘调用。"""
    rt     = config.get("runtime")
    bar    = rt.get("bar", "1m")
    now    = time.time()
    with _CACHE_LOCK:
        cached = _CANDLE_CACHE.get(bar)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]

    inst_id = rt.get("inst_id", "BTC-USDT-SWAP")
    data    = okx_client.get_candles(inst_id, bar=bar, limit=limit)
    if not data:
        log.warning("direction_filter: 抓取 K 线失败，返回空列表")
        return []
    candles = list(reversed(data))   # OKX 返回 newest-first，转为 oldest-first
    with _CACHE_LOCK:
        _CANDLE_CACHE[bar] = (now, candles)
    return candles


# ──────────────────── 主判断入口 ────────────────────

def check_direction(side: str,
                    candles: list = None,
                    threshold: int = None,
                    obi: float = None,
                    aggressive_buy_ratio: float = None,
                    funding_rate: float = None,
                    long_short_ratio: float = None) -> tuple:
    """判断是否符合开多/开空条件。

    Args:
        side     : "long" 或 "short"
        candles  : oldest-first K 线列表 [ts_ms, open, high, low, close, vol, ...]
                   传 None 时自动从 OKX 抓取（实盘用，带缓存）
        threshold: 通过分数门槛绝对值；None 时读 config direction_filter.threshold（默认 6）
        obi                  : 订单簿不平衡度（可选，实盘专用）
        aggressive_buy_ratio : 主动买入比（可选，实盘专用）
        funding_rate         : 资金费率（可选，实盘专用）
        long_short_ratio     : 多空比（可选，实盘专用）

    Returns:
        (allowed: bool, score: int, detail: dict)
        - allowed : True 表示可以交易，False 表示不符合条件，跳过本次下单
        - score   : 总分，范围 [-14, +14]
        - detail  : 各维度分数与元信息
    """
    df_cfg = config.get("direction_filter") or {}

    # 总开关
    if not df_cfg.get("enabled", True):
        return True, 0, {"skip": "disabled"}

    if threshold is None:
        threshold = int(df_cfg.get("threshold", 6))

    # K 线数据（回测传入 / 实盘自动拉取）
    if candles is None:
        candles = _fetch_candles_cached()

    if len(candles) < 10:
        log.warning("direction_filter: K 线数据不足（%d 根），直接放行", len(candles))
        return True, 0, {"skip": "insufficient_data", "candles": len(candles)}

    closes = [float(c[4]) for c in candles]

    s_trend = score_trend(closes)
    s_vol   = score_volume(candles,
                           vol_window=int(df_cfg.get("vol_window", 20)),
                           breakout_window=int(df_cfg.get("breakout_window", 20)),
                           diverge_window=int(df_cfg.get("diverge_window", 20)))
    s_micro = score_microstructure(obi, aggressive_buy_ratio)
    s_sent  = score_sentiment(funding_rate, long_short_ratio)
    total   = s_trend + s_vol + s_micro + s_sent

    detail = {
        "trend":     s_trend,
        "volume":    s_vol,
        "micro":     s_micro,
        "sentiment": s_sent,
        "total":     total,
        "threshold": threshold,
        "candles":   len(candles),
    }

    if side == "long":
        allowed = total >= threshold
    elif side == "short":
        allowed = total <= -threshold
    else:
        log.error("direction_filter: 未知 side=%s", side)
        allowed = False

    mark = "✅" if allowed else "🚫"
    log.info("direction_filter %s %s | 趋势=%+d 量=%+d 微观=%+d 情绪=%+d → 总分=%+d (阈值±%d)",
             mark, side, s_trend, s_vol, s_micro, s_sent, total, threshold)

    return allowed, total, detail
