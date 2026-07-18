"""恐慌贪婪指数（Fear & Greed Index）开仓过滤模块。

数据来源：https://api.alternative.me/fng/?limit=0
每日更新一次，默认缓存 1 小时（可配置）。

开仓规则（score 范围 0–100）：
  score ≤ 20 或 score ≥ 80  → 停止所有开仓（极端区间）
  20 < score < 40           → 禁止开多（恐慌期）
  40 ≤ score ≤ 60           → 不限制方向（中性区）
  60 < score < 80           → 禁止开空（贪婪期）

趋势规则（近 trend_days 日线性斜率，每日变化量）：
  斜率 > +trend_threshold   → 情绪持续上升，禁止开空
  斜率 < −trend_threshold   → 情绪持续下降，禁止开多

接口不可用时：默认禁止（保守策略）。
回测时传入 ts_sec 使用对应历史分值。
"""
import datetime
import json
import threading
import time
import urllib.request

from bin import config
from bin.logger import get_logger

log = get_logger("fng_filter")

_FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {}   # ts → 缓存时间戳，data → [{value, timestamp}, ...]


# ──────────────────── 数据拉取与缓存 ────────────────────

def _fetch_raw() -> list:
    """从 alternative.me 拉取全量历史（newest-first）。失败返回空列表。"""
    try:
        req = urllib.request.Request(_FNG_URL, headers={"User-Agent": "btcusdt-bot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode())
            data = raw.get("data", [])
            log.info("FNG 数据拉取成功，共 %d 条历史", len(data))
            return data
    except Exception as e:
        log.warning("FNG 数据拉取失败: %s", e)
        return []


def get_data() -> list:
    """获取 FNG 全量历史（带缓存，TTL 见 config fng_filter.cache_ttl，默认 3600s）。

    返回 [{value: str, timestamp: str, ...}, ...]，newest-first。
    """
    cfg  = config.get("fng_filter") or {}
    ttl  = int(cfg.get("cache_ttl", 3600))
    now  = time.time()

    with _CACHE_LOCK:
        if _CACHE.get("data") and now - _CACHE.get("ts", 0) < ttl:
            return _CACHE["data"]

    data = _fetch_raw()
    if data:
        with _CACHE_LOCK:
            _CACHE["data"] = data
            _CACHE["ts"]   = now
    return data


# ──────────────────── 工具函数 ────────────────────

def _linear_slope(values: list) -> float:
    """计算一组数值的线性回归斜率（每步变化量）。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num    = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denom  = sum((i - x_mean) ** 2 for i in range(n))
    return num / denom if denom else 0.0


def _value_for_ts(ts_sec: int, all_data: list):
    """从全量数据中找 ts_sec 当日（或最近一日）的 FNG 分值。未找到返回 None。"""
    target = datetime.date.fromtimestamp(ts_sec)
    for item in all_data:   # newest-first
        day = datetime.date.fromtimestamp(int(item["timestamp"]))
        if day <= target:
            return int(item["value"])
    return None


def _trend_slope(ts_sec: int, all_data: list, trend_days: int) -> float:
    """计算 ts_sec 当天之前（含当天）连续 trend_days 天的 FNG 斜率。"""
    target = datetime.date.fromtimestamp(ts_sec)
    vals   = []
    for item in reversed(all_data):   # oldest-first 遍历
        day = datetime.date.fromtimestamp(int(item["timestamp"]))
        if day <= target:
            vals.append(int(item["value"]))
    recent = vals[-trend_days:] if len(vals) >= trend_days else vals
    return _linear_slope(recent)


# ──────────────────── 主判断接口 ────────────────────

def check_open(side: str, ts_sec: int = None, all_data: list = None) -> tuple:
    """判断是否允许开仓（实盘/回测通用）。

    Args:
        side     : "long" 或 "short"
        ts_sec   : 目标时间戳（秒）；None → 取当前时间（实盘）
        all_data : 预先拉取的 FNG 数据（回测中批量传入，避免重复请求）；
                   None → 自动从缓存/接口获取

    Returns:
        (allowed: bool, reason: str)
    """
    cfg = config.get("fng_filter") or {}

    if not cfg.get("enabled", True):
        return True, "fng_disabled"

    if ts_sec is None:
        ts_sec = int(time.time())

    trend_days = int(cfg.get("trend_days",       5))
    trend_thr  = float(cfg.get("trend_threshold", 3.0))

    if all_data is None:
        all_data = get_data()

    if not all_data:
        log.warning("数据不可用，拒绝开仓（保守策略）side=%s", side)
        return False, "数据不可用"

    value = _value_for_ts(ts_sec, all_data)
    if value is None:
        log.warning("FNG 无对应日期数据 ts=%d，拒绝开仓", ts_sec)
        return False, "FNG无对应日期数据"

    slope = _trend_slope(ts_sec, all_data, trend_days)

    # ── 极端区间：停止所有开仓 ──
    if value <= 20:
        return False, f"市场情绪极度低迷，风险期停止所有开仓，情绪指数:{value}"
    if value >= 80:
        return False, f"市场情绪极度高涨，风险期停止所有开仓，情绪指数:{value}"

    # ── 方向限制 + 趋势叠加 ──
    if side == "long":
        if value < 40:
            return False, f"市场情绪低迷，禁止开多，情绪指数:{value}"
        if slope < -trend_thr:
            return False, f"市场情绪下降(slope={slope:.1f}<-{trend_thr})，禁止开多"

    elif side == "short":
        if value > 60:
            return False, f"市场情绪高涨，禁止开空，情绪指数:{value}"
        if slope > trend_thr:
            return False, f"市场情绪上升(slope={slope:.1f}>+{trend_thr})，禁止开空"

    log.debug("FNG允许 side=%s value=%d slope=%.1f", side, value, slope)
    return True, f"FNG={value} slope={slope:.1f}"
