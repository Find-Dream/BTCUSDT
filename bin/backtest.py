"""回溯引擎：完整策略模拟版。

在内存中维护一套临时状态（宏观形势 / gap / 仓位 / pos_ok），
逐根 K 线按 mark.py 相同的逻辑模拟开仓、加仓、止盈、止损，
实现与实盘一致的策略验证。
"""
import time as _time
import threading

from bin import config, okx_client, direction_filter as _df, fng_filter as _fng
from bin import monitor as _monitor
from bin.logger import get_logger
from model.fingerprint import fingerprint
from model.position import FEE_RATE, CONTRACT_SIZE, add_pos_trigger, new_avg_price, take_profit
from model.gap import gap_rule_for5
from model.situation import situation as calc_situation

log = get_logger("backtest")

_BAR_SEC = {"1m": 60, "5m": 300, "15m": 900}
_WARMUP  = 30   # 热身缓冲根数

# 动作类型（扩展到8种）
ACT = {
    1: ("开多", "#22c55e"),
    2: ("平多", "#22d3ee"),
    3: ("开空", "#f87171"),
    4: ("平空", "#fb923c"),
    5: ("加多", "#86efac"),
    6: ("加空", "#fda4af"),
    7: ("止损多", "#ef4444"),
    8: ("止损空", "#f97316"),
}


# ──────────────────── 临时交易状态 ────────────────────

class _State:
    """回测期间的全量临时状态，不读写数据库。"""

    def __init__(self, sz, pos_ok=3, strat=None):
        strat = strat or {}
        self.sz       = int(sz)
        self.pos_ok   = pos_ok

        # 仓位
        self.long_avg   = 0.0; self.long_start = 0.0; self.long_sz   = 0
        self.short_avg  = 0.0; self.short_start= 0.0; self.short_sz  = 0
        self.long_add_count  = 0   # 当前多头已加仓次数
        self.short_add_count = 0   # 当前空头已加仓次数

        # gap 状态
        self.gap_num   = 0        # gap_rule_num（0/1）
        self.prev_price = None
        self.recent_gaps = []     # newest-first，最多保留 10

        # 价格历史（ts, close），用于宏观均价
        self.price_hist = []      # [(ts_sec, close), ...]

        # 宏观形势缓存
        self._sit24 = 0; self._sit1 = 0; self._sit_ts = 0

        # 策略参数（缓存）
        self.amp_open   = strat.get("amp_open",   10)
        self.amp_close  = strat.get("amp_close",  20)
        self.day_buf    = strat.get("day_range_buffer", 0.05)
        self.gap_num_v  = strat.get("gap_num",     30)
        self.gap_num_b  = strat.get("gap_num_big", 200)
        self.add_gap       = strat.get("add_pos_gap",       10)
        self.add_sz_v      = strat.get("add_pos_sz",        3)
        self.add_enabled   = strat.get("add_pos_enabled",   True)
        self.add_max_times = int(strat.get("add_pos_max_times", 3))
        self.tp_long    = strat.get("take_profit_long",  1.001)
        self.tp_short   = strat.get("take_profit_short", 0.999)
        self.sit_ext    = strat.get("situation_extreme",  1500)
        self.sit_pct    = strat.get("situation_1h_pct",  0.01)

    # ---- 价格更新 ----
    def tick(self, ts, close):
        """每根 K 线收盘后调用，更新价格历史和 gap 序列。"""
        self.price_hist.append((ts, float(close)))
        # 只保留最近 72h（gap 无需那么长）
        cutoff = ts - 86400 * 3
        self.price_hist = [(t, p) for t, p in self.price_hist if t >= cutoff]

        if self.prev_price is not None:
            diff = float(close) - self.prev_price
            self.recent_gaps.insert(0, diff)   # newest-first
            if len(self.recent_gaps) > 10:
                self.recent_gaps.pop()
        self.prev_price = float(close)

    # ---- gap 判定 ----
    def compute_gap(self):
        if len(self.recent_gaps) < 10:
            return 0
        gap_rule, new_num = gap_rule_for5(
            self.recent_gaps, self.gap_num,
            num=self.gap_num_v, num_b=self.gap_num_b)
        self.gap_num = new_num
        return gap_rule

    # ---- 宏观形势 ----
    def compute_situation(self, ts):
        # 每根 K 线刷新一次（1m 周期=每分钟）
        now = ts

        def _avg(secs):
            cut = now - secs
            vals = [p for t, p in self.price_hist if t >= cut]
            return sum(vals) / len(vals) if vals else None

        avg_1h  = _avg(3600)
        avg_24h = _avg(86400)
        avg_72h = _avg(86400 * 3)
        last    = self.price_hist[-1][1] if self.price_hist else None

        if None in (avg_1h, avg_24h, avg_72h, last):
            return 0, 0   # 数据不足，全放行
        s24, s1 = calc_situation(avg_1h, avg_24h, avg_72h, last,
                                 extreme=self.sit_ext, pct_1h=self.sit_pct)
        self._sit24 = s24; self._sit1 = s1; self._sit_ts = now
        return s24, s1

    # ---- 24h 高低价 ----
    def day_hl(self, candles_window):
        """传入最近 12h 的蜡烛数组（oldest-first），返回 (high, low)。"""
        if not candles_window:
            return None, None
        high = max(float(r[2]) for r in candles_window)
        low  = min(float(r[3]) for r in candles_window)
        return high, low

    # ---- 尾数过滤 ----
    @staticmethod
    def tail_ok_long(price):
        s = str(int(price))
        return not (s[-3] == '9' or s[-4] == '9' or s[-4] == '0') if len(s) >= 4 else True

    @staticmethod
    def tail_ok_short(price):
        s = str(int(price))
        return not (s[-3] == '0' or s[-4] == '0' or s[-4] == '9') if len(s) >= 4 else True

    # ---- 仓位操作 ----
    def open_long(self, price):
        self.long_avg   = price
        self.long_start = price
        self.long_sz    = self.sz

    def close_long(self):
        avg, sz = self.long_avg, self.long_sz
        self.long_avg = self.long_start = 0.0; self.long_sz = 0
        self.long_add_count = 0   # 平仓后重置计数
        return avg, sz

    def add_long(self, price):
        new_avg, new_sz = new_avg_price(self.long_avg, self.long_sz, price, self.add_sz_v)
        self.long_avg = new_avg; self.long_sz = new_sz
        self.long_add_count += 1
        return new_avg, new_sz, self.add_sz_v

    def open_short(self, price):
        self.short_avg   = price
        self.short_start = price
        self.short_sz    = self.sz

    def close_short(self):
        avg, sz = self.short_avg, self.short_sz
        self.short_avg = self.short_start = 0.0; self.short_sz = 0
        self.short_add_count = 0   # 平仓后重置计数
        return avg, sz

    def add_short(self, price):
        new_avg, new_sz = new_avg_price(self.short_avg, self.short_sz, price, self.add_sz_v)
        self.short_avg = new_avg; self.short_sz = new_sz
        self.short_add_count += 1
        return new_avg, new_sz, self.add_sz_v

    def flip_pos_ok(self, stopped_side):
        if self.pos_ok == 3:
            self.pos_ok = 2 if stopped_side == "long" else 1


# ──────────────────── K 线拉取 ────────────────────

def _fetch_range(bar, start_ts, end_ts, log_cb=None, progress_cb=None):
    def _log(msg):
        log.info(msg)
        if log_cb: log_cb(msg)

    rt = config.get("runtime")
    inst_id = rt.get("inst_id", "BTC-USDT-SWAP")
    bar_sec  = _BAR_SEC.get(bar, 60)
    fetch_start_ms = (start_ts - _WARMUP * bar_sec) * 1000
    fetch_end_ms   = end_ts * 1000
    estimated = max(1, (end_ts - start_ts) // bar_sec)
    _log(f"开始拉取 {bar} K 线，预计约 {estimated} 根，每页 300 根…")

    all_data = []; after_ms = fetch_end_ms + bar_sec * 1000; page = 0
    while True:
        data = okx_client.get_history_candles(inst_id, bar=bar, limit=300, after=after_ms)
        if not data:
            data = okx_client.get_candles(inst_id, bar=bar, limit=300, after=after_ms)
        if not data:
            _log("⚠ OKX 返回空数据，停止拉取"); break
        page += 1
        relevant = [d for d in data if fetch_start_ms <= int(d[0]) <= fetch_end_ms]
        all_data.extend(relevant)
        oldest_ts = int(data[-1][0]) // 1000
        newest_ts = int(data[0][0])  // 1000
        _log(f"第 {page} 页：{_time.strftime('%m-%d %H:%M', _time.localtime(oldest_ts))} → "
             f"{_time.strftime('%m-%d %H:%M', _time.localtime(newest_ts))}，"
             f"本页 {len(data)} 根，累计有效 {len(all_data)} 根")
        # 拉取阶段占总进度 0-40%
        if progress_cb:
            pct = min(39.99, len(all_data) / max(1, estimated) * 40)
            progress_cb(round(pct, 2))
        if int(data[-1][0]) <= fetch_start_ms: break
        after_ms = int(data[-1][0])
        _time.sleep(0.15)

    seen = {}
    for d in all_data: seen[int(d[0])] = d
    result = sorted(seen.values(), key=lambda x: int(x[0]))
    _log(f"✓ 数据拉取完成，共 {len(result)} 根（含 {_WARMUP} 根热身缓冲）")
    if progress_cb: progress_cb(40.0)
    return result


# ──────────────────── 主回测 ────────────────────

def run(bar, start_ts, end_ts, table="model_1m", log_cb=None, progress_cb=None):
    """完整策略回测。"""
    def _log(msg):
        log.info(msg)
        if log_cb: log_cb(msg)

    # 确保缓存
    with _monitor._CACHE_LOCK:
        cache_empty = table not in _monitor._CACHE
    if cache_empty:
        _log(f"模型缓存为空，正在从数据库加载 {table}…")
        _monitor.reload_cache(table)
    with _monitor._CACHE_LOCK:
        model_count = len(_monitor._CACHE.get(table, []))
    _log(f"模型库 {table} 已加载 {model_count} 条到内存")

    # 拉取数据
    data = _fetch_range(bar, start_ts, end_ts, log_cb=log_cb, progress_cb=progress_cb)
    if len(data) < 25:
        return {"error": "历史数据不足（< 25 根），请调整时间范围"}

    # 定位回测起点
    start_ms  = start_ts * 1000
    start_idx = 0
    for i, d in enumerate(data):
        if int(d[0]) >= start_ms:
            start_idx = i; break

    cfg   = config.get("strategy")
    tcfg  = config.get("trade")
    band10    = cfg.get("ma_spot_band_10", 10)
    band20    = cfg.get("ma_spot_band_20", 20)
    line_band = cfg.get("ma_line_band", 10)
    base_sz   = int(tcfg.get("start_sz", 3))
    # 回测专用方向过滤阈值（回测只有趋势+成交量两维，满分±8，独立设置）
    _bt_df_thr = int((config.get("direction_filter") or {}).get("backtest_threshold", 4))

    state = _State(sz=base_sz, pos_ok=3, strat=cfg)

    # 预拉取历史市场情绪数据（回测期间复用，避免循环内重复请求）
    _fng_data = _fng.get_data()
    if not _fng_data:
        _log("⚠ 市场情绪数据拉取失败，回测期间市场情绪数据过滤将全部拒绝开仓")
    else:
        _log(f"历史市场情绪数据加载成功，共 {len(_fng_data)} 条")

    total_scan = len(data) - max(24, start_idx)
    _log(f"开始完整策略模拟，共 {total_scan} 根，含宏观/市场情绪/极端情况/仓位全闸门…")

    signals = []   # 所有动作（开/平/加/止损）
    trades  = []   # 完整成对成交（含P&L）
    _candle_codes: dict = {}   # chart_idx → 15码，供建议晋升去重用
    _last_pct_sent = 40.0      # 拉取阶段已到40%

    bar_sec  = _BAR_SEC.get(bar, 60)
    HL_SECS  = 43200   # 12h

    for i in range(max(24, start_idx), len(data)):
        r      = data[i]
        ts_ms  = int(r[0])
        ts_sec = ts_ms // 1000
        close  = float(r[4])
        open_  = float(r[1])
        high_  = float(r[2])
        low_   = float(r[3])
        # 模拟阶段占总进度 40-99%（留1%给后处理）
        if progress_cb and total_scan > 0:
            done = i - max(24, start_idx) + 1
            cur_pct = round(40.0 + done / total_scan * 59.0, 2)
            if cur_pct - _last_pct_sent >= 0.1:
                progress_cb(cur_pct)
                _last_pct_sent = cur_pct

        chart_idx = i - start_idx

        # ── 状态更新 ──
        state.tick(ts_sec, close)
        gap_rule = state.compute_gap()
        s24, s1  = state.compute_situation(ts_sec)

        # 24h 高低（取最近12h 的蜡烛）
        hl_start = ts_sec - HL_SECS
        hl_window = [d for d in data[:i+1] if int(d[0])//1000 >= hl_start]
        day_high, day_low = state.day_hl(hl_window)
        if day_high is None: day_high = day_low = close
        buf = (day_high - day_low) * state.day_buf

        t = _time.strftime("%m-%d %H:%M", _time.localtime(ts_sec))

        # ── 指纹匹配 ──
        window = list(reversed(data[max(0, i-29):i+1]))
        model_type = model_id = None
        if len(window) >= 25:
            try:
                codes = fingerprint(window, band10, band20, line_band)
                _candle_codes[chart_idx] = codes   # 缓存指纹供建议晋升去重
                hit   = _monitor._match(table, codes, 9)
                if hit:
                    model_id   = hit[0]
                    model_type = hit[1]
            except Exception:
                pass

        def _act(atype, price, sz, mid=None, avg=None, df_score=None):
            name = ACT[atype][0]
            _log(f"  {name} @ {t}  价格={price:.2f}  sz={sz}"
                 + (f"  模型#{mid}" if mid else "")
                 + (f"  均价={avg:.2f}" if avg else "")
                 + (f"  df={df_score:+d}" if df_score is not None else ""))
            signals.append({
                "idx": chart_idx, "type": atype, "price": price,
                "sz": sz, "time": t, "ts": ts_sec,
                "model_id": mid,
                "direction_score": df_score,
            })

        # ══ 多头持仓逻辑 ══
        if state.long_sz > 0:
            avg_l = state.long_avg

            # 止损（gap 暴跌）
            if gap_rule == 2:
                avg_p, sz = state.close_long()
                _act(7, close, sz, avg=avg_p)
                trades.append(_mk_trade("long", avg_p, close, sz, "止损", ts_sec, t, t))
                state.flip_pos_ok("long")
                _log(f"    止损后 pos_ok → {state.pos_ok}")

            # 止盈（有平多信号 且 价格越过均价×1.001）
            elif close > avg_l:
                if (model_type == 2
                        and take_profit(avg_l, close, "long", state.tp_long)):
                    _ampl_ok = (open_ - close) > state.amp_close
                    avg_p, sz = state.close_long()
                    _act(2, close, sz, mid=model_id, avg=avg_p)
                    trades.append(_mk_trade("long", avg_p, close, sz, "止盈", ts_sec, t, t))

            # 亏损：马丁加仓（受开关和次数上限约束）
            else:
                if (state.add_enabled
                        and state.long_add_count < state.add_max_times
                        and add_pos_trigger(state.long_start, close, state.add_gap, "long")):
                    df_add = (config.get("direction_filter") or {}).get("apply_to_add", False)
                    if df_add:
                        bt_candles = data[max(0, i - 79):i + 1]
                        df_ok, df_score, _ = _df.check_direction("long", candles=bt_candles,
                                                                   threshold=_bt_df_thr)
                    else:
                        df_ok, df_score = True, None
                    if df_ok:
                        new_avg, new_sz, add_s = state.add_long(close)
                        _act(5, close, add_s, avg=new_avg, df_score=df_score)
                    else:
                        _log(f"  加多@ {t} 下行趋势，禁止开多 score={df_score:+d}")

        # ══ 空头持仓逻辑 ══
        elif state.short_sz > 0:
            avg_s = state.short_avg

            # 止损（gap 暴涨）
            if gap_rule == 1:
                avg_p, sz = state.close_short()
                _act(8, close, sz, avg=avg_p)
                trades.append(_mk_trade("short", avg_p, close, sz, "止损", ts_sec, t, t))
                state.flip_pos_ok("short")
                _log(f"    止损后 pos_ok → {state.pos_ok}")

            # 止盈
            elif close < avg_s:
                if (model_type == 4
                        and take_profit(avg_s, close, "short", tp_short=state.tp_short)):
                    avg_p, sz = state.close_short()
                    _act(4, close, sz, mid=model_id, avg=avg_p)
                    trades.append(_mk_trade("short", avg_p, close, sz, "止盈", ts_sec, t, t))

            # 亏损：马丁加仓（受开关和次数上限约束）
            else:
                if (state.add_enabled
                        and state.short_add_count < state.add_max_times
                        and add_pos_trigger(state.short_start, close, state.add_gap, "short")):
                    df_add = (config.get("direction_filter") or {}).get("apply_to_add", False)
                    if df_add:
                        bt_candles = data[max(0, i - 79):i + 1]
                        df_ok, df_score, _ = _df.check_direction("short", candles=bt_candles,
                                                                   threshold=_bt_df_thr)
                    else:
                        df_ok, df_score = True, None
                    if df_ok:
                        new_avg, new_sz, add_s = state.add_short(close)
                        _act(6, close, add_s, avg=new_avg, df_score=df_score)
                    else:
                        _log(f"  加空@ {t} 上行趋势，禁止开空 score={df_score:+d}")

        # ══ 尝试开仓（空仓状态）══
        else:
            if model_type == 1 and state.long_sz == 0:
                # 振幅门
                if (close - open_) > state.amp_open:
                    # 形状门
                    spot, l5, l10 = codes[0], codes[1], codes[2]
                    shape_ok = (spot != 100 and l5 == 600 and l10 == 600) or \
                               (spot != 100 and l5 == 500 and l10 == 500)
                    if (shape_ok
                            and state.tail_ok_long(close)
                            and state.pos_ok in (1, 3)
                            and s24 in (0, 1) and s1 in (0, 1)
                            and (day_high - close) > buf):
                        bt_candles = data[max(0, i - 79):i + 1]   # oldest-first
                        df_ok, df_score, _ = _df.check_direction("long", candles=bt_candles,
                                                                    threshold=_bt_df_thr)
                        if df_ok:
                            fng_ok, fng_reason = _fng.check_open("long", ts_sec, _fng_data)
                        if df_ok and fng_ok:
                            state.open_long(close)
                            _act(1, close, base_sz, mid=model_id, df_score=df_score)
                        elif not df_ok:
                            _log(f"  开多@ {t} 下行趋势，禁止开多 score={df_score:+d}")
                        else:
                            _log(f"  开多@ {t} {fng_reason}")

            elif model_type == 3 and state.short_sz == 0:
                if (open_ - close) > state.amp_open:
                    spot, l5, l10 = codes[0], codes[1], codes[2]
                    shape_ok = (spot != 100 and l5 == 600 and l10 == 600) or \
                               (spot != 100 and l5 == 500 and l10 == 500)
                    if (shape_ok
                            and state.tail_ok_short(close)
                            and state.pos_ok in (2, 3)
                            and s24 in (0, 2) and s1 in (0, 2)
                            and (close - day_low) > buf):
                        bt_candles = data[max(0, i - 79):i + 1]   # oldest-first
                        df_ok, df_score, _ = _df.check_direction("short", candles=bt_candles,
                                                                    threshold=_bt_df_thr)
                        if df_ok:
                            fng_ok, fng_reason = _fng.check_open("short", ts_sec, _fng_data)
                        if df_ok and fng_ok:
                            state.open_short(close)
                            _act(3, close, base_sz, mid=model_id, df_score=df_score)
                        elif not df_ok:
                            _log(f"  开空@ {t} 上行趋势，禁止开空 score={df_score:+d}")
                        else:
                            _log(f"  开空@ {t} {fng_reason}")

    total_scan = len(data) - max(24, start_idx)
    _log(f"扫描完成：动作 {len(signals)} 条，成对成交 {len(trades)} 笔")

    # ── 失败模型分析：开仓后 N 根 K 线价格未如期移动 ──
    _CHECK_BARS = 5
    _fail_cnt: dict = {}   # (model_id, side) → 失败次数
    for sig in signals:
        if sig["type"] not in (1, 3):
            continue
        mid = sig.get("model_id")
        if mid is None:
            continue
        di = sig["idx"] + start_idx
        ci = min(di + _CHECK_BARS, len(data) - 1)
        later_close = float(data[ci][4])
        if sig["type"] == 1 and later_close <= sig["price"]:   # 开多但价格未涨
            _fail_cnt[(mid, "long")] = _fail_cnt.get((mid, "long"), 0) + 1
        elif sig["type"] == 3 and later_close >= sig["price"]: # 开空但价格未跌
            _fail_cnt[(mid, "short")] = _fail_cnt.get((mid, "short"), 0) + 1

    failed_models = sorted(
        [{"model_id": mid, "side": s, "fail_count": c}
         for (mid, s), c in _fail_cnt.items()],
        key=lambda x: -x["fail_count"]
    )
    _log(f"失败模型统计：{len(failed_models)} 个模型ID 存在价格反向情况")

    # ── 建议晋升点位：有足够振幅、无模型命中、且指纹不在模型库中的 K 线 ──
    _open_idxs = {sig["idx"] for sig in signals if sig["type"] in (1, 3)}
    _suggests: list = []
    for i in range(max(30, start_idx), len(data)):
        ci = i - start_idx
        if ci in _open_idxs:
            continue   # 已有模型命中，跳过
        r = data[i]
        ts_sec = int(r[0]) // 1000
        op, cl = float(r[1]), float(r[4])
        amp_up   = cl - op
        amp_down = op - cl
        if amp_up <= state.amp_open and amp_down <= state.amp_open:
            continue
        # 检查指纹是否已存在于模型库（复用主循环缓存的15码）
        codes = _candle_codes.get(ci)
        if codes and _monitor._match(table, codes, 9):
            continue   # 指纹已在模型库，不重复建议
        if amp_up > state.amp_open:
            _suggests.append({
                "idx": ci, "ts": ts_sec,
                "time": _time.strftime("%m-%d %H:%M", _time.localtime(ts_sec)),
                "type": 1, "price": cl, "amp": round(amp_up, 2),
            })
        elif amp_down > state.amp_open:
            _suggests.append({
                "idx": ci, "ts": ts_sec,
                "time": _time.strftime("%m-%d %H:%M", _time.localtime(ts_sec)),
                "type": 3, "price": cl, "amp": round(amp_down, 2),
            })

    _suggests.sort(key=lambda x: -x["amp"])
    suggest_promotes = _suggests[:50]
    _log(f"建议晋升点位：共 {len(_suggests)} 个（已排除指纹重复），筛选前 {len(suggest_promotes)} 条")

    # ── 图表数据 ──
    chart_data = data[start_idx:]
    closes = [float(d[4]) for d in chart_data]
    times, tslist, candles, mas, volumes = [], [], [], {"m5":[],"m10":[],"m20":[]}, []
    for j, d in enumerate(chart_data):
        ts = int(d[0]) // 1000
        times.append(_time.strftime("%m-%d %H:%M", _time.localtime(ts)))
        tslist.append(ts)
        candles.append([float(d[1]), float(d[4]), float(d[3]), float(d[2])])
        mas["m5"].append(_ma(closes, j, 5))
        mas["m10"].append(_ma(closes, j, 10))
        mas["m20"].append(_ma(closes, j, 20))
        volumes.append(float(d[5]))

    # ── 汇总 ──
    total_gross = round(sum(t["gross"] for t in trades), 2)
    total_fee   = round(sum(t["fee"]   for t in trades), 2)
    total_net   = round(sum(t["net"]   for t in trades), 2)
    win_count   = sum(1 for t in trades if t["net"] > 0)

    _log(f"✓ 回测完成 | 净收益 {total_net} USDT  手续费 {total_fee}  "
         f"胜率 {round(win_count/len(trades)*100,1) if trades else 0}%")

    return {
        "times":times, "ts":tslist, "candles":candles, "ma":mas, "volumes":volumes,
        "signals":signals, "trades":trades,
        "summary": {
            "total":     len(trades), "win": win_count,
            "lose":      len(trades) - win_count,
            "win_rate":  round(win_count/len(trades)*100,1) if trades else 0,
            "gross":     total_gross, "fee": total_fee, "net": total_net,
            "open_signals":  sum(1 for s in signals if s["type"] in (1,3)),
            "close_signals": sum(1 for s in signals if s["type"] in (2,4,7,8)),
        },
        "failed_models":   failed_models,
        "suggest_promotes": suggest_promotes,
    }


def _mk_trade(side, open_p, close_p, sz, reason, ts, open_t, close_t):
    multiplier = sz * CONTRACT_SIZE
    gross = round((close_p - open_p if side == "long" else open_p - close_p) * multiplier, 4)
    fee   = round((open_p + close_p) * FEE_RATE * multiplier, 4)
    return {"side": side, "open_time": open_t, "open_price": open_p,
            "close_time": close_t, "close_price": close_p, "sz": sz, "reason": reason,
            "gross": gross, "fee": fee, "net": round(gross - fee, 4)}


def _ma(closes, idx, n):
    seg = closes[max(0,idx-n+1):idx+1]
    return round(sum(seg)/n,2) if len(seg)>=n else None
