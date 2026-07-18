"""策略决策引擎（复刻老项目 mark.py 的 main 逻辑）。

职责：读取实时价与命中信号，经多重闸门决定 开仓 / 止盈平仓 / 加仓 / 止损，
把决策写入 pos / pos_log，再交由 trader 执行。

闸门（开多，开空对称）：
  1. 该方向空仓  2. 价格尾数过滤(百位≠9,千位≠9且≠0)  3. pos_ok 允许方向
  4. 存在新的开多信号(type=1)  5. 形状门(spot≠100 且 line5=line10=500)
  6. situation 宏观(24h∈{0,1} 且 1h∈{0,1})  7. 不在 24h 高点 5% 缓冲内
止盈：盈利 且 存在平仓信号 且 价格越过 均价×1.001(多)/×0.999(空)
止损/加仓：亏损时，gap 暴跌(2)/暴涨(1) 强制平仓；否则马丁加仓
"""
import time

from bin import config, kline as kline_bin, trader, direction_filter, fng_filter
from bin.logger import get_logger
from data import pos_dao, signal_dao
from model import situation as situation_model
from model import gap as gap_model
from model import position as pos_math

log = get_logger("mark")


# ---------------- 宏观形势（带 60 秒缓存，复刻老项目）----------------
def get_situation():
    strat = config.get("strategy")
    cached = signal_dao.latest_situation()
    now = time.time()
    if cached and now < cached[-1] + 60:
        return cached[1], cached[2]

    avg_1h = signal_dao.avg_last(3600)
    avg_24h = signal_dao.avg_last(86400)
    avg_72h = signal_dao.avg_last(86400 * 3)
    last = signal_dao.latest_last()
    if None in (avg_1h, avg_24h, avg_72h, last):
        return 0, 0  # 数据不足，全放行
    s24, s1 = situation_model.situation(
        avg_1h, avg_24h, avg_72h, last,
        extreme=strat.get("situation_extreme", 1500),
        pct_1h=strat.get("situation_1h_pct", 0.01))
    signal_dao.add_situation(s24, s1, now)
    return s24, s1


# ---------------- 暴涨暴跌（写 last_gap + 判定）----------------
def update_gap(last):
    strat = config.get("strategy")
    signal_dao.add_gap(last)
    gaps = signal_dao.last_n_gaps(10)
    prev = signal_dao.get_gap_rule_num()
    gap_rule, new_num = gap_model.gap_rule_for5(
        gaps, prev, num=strat.get("gap_num", 30), num_b=strat.get("gap_num_big", 200))
    signal_dao.set_gap_rule_num(new_num)
    return gap_rule


# ---------------- 主决策 ----------------
def run(jg_list):
    """执行一次策略决策；返回本次动作描述列表。"""
    if len(jg_list) < 2:
        return []
    strat = config.get("strategy")
    tcfg = config.get("trade")
    now = time.time()
    last = float(jg_list[0][4])
    time_end = int(now) - 5
    actions = []

    pos_ok = pos_dao.get_pos_ok()
    start_sz = tcfg.get("start_sz", 3)

    # 价格尾数
    last_100 = int(str(int(last))[-3])
    last_1000 = int(str(int(last))[-4])

    gap_rule = update_gap(last)
    day_high, day_low = kline_bin.day_high_low("1m")
    if day_high is None:
        day_high, day_low = last, last
    buffer = (float(day_high) - float(day_low)) * strat.get("day_range_buffer", 0.05)

    pos_long = pos_dao.get_pos("long")
    pos_short = pos_dao.get_pos("short")

    # ===== 多头 =====
    actions += _handle_long(pos_long, last, last_100, last_1000, pos_ok,
                            time_end, day_high, buffer, start_sz, gap_rule, strat, now)
    # ===== 空头 =====
    actions += _handle_short(pos_short, last, last_100, last_1000, pos_ok,
                             time_end, day_low, buffer, start_sz, gap_rule, strat, now)

    # 有决策则触发执行
    if actions:
        result = trader.execute_latest()
        log.info("执行结果: %s", result)
    return actions


def _handle_long(pos_long, last, last_100, last_1000, pos_ok, time_end,
                 day_high, buffer, start_sz, gap_rule, strat, now):
    acts = []
    in_pos = pos_long and pos_long[3] and float(pos_long[3]) != 0  # last 列非 0 视为持仓
    avg = float(pos_long[3]) if pos_long else 0

    if not in_pos:
        # ---- 开多闸门 ----
        if last_100 == 9 or last_1000 == 9 or last_1000 == 0:
            return acts
        if pos_ok not in (1, 3):
            return acts
        sig = signal_dao.select_signal(1, time_end)
        if not sig:
            return acts
        s24, s1 = get_situation()
        if s24 not in (0, 1) or s1 not in (0, 1):
            return acts
        if (float(day_high) - float(last)) <= buffer:
            log.info("当前价在 24h 高点缓冲内，跳过开多")
            return acts
        # ── 方向过滤器 ──
        df_ok, df_score, _ = direction_filter.check_direction("long")
        if not df_ok:
            log.info("下行趋势，禁止开多（score=%+d）@%s", df_score, last)
            return acts
        # ── 恐慌贪婪指数过滤 ──
        fng_ok, fng_reason = fng_filter.check_open("long")
        if not fng_ok:
            log.info("市场情绪低迷，禁止开多：%s @%s", fng_reason, last)
            return acts
        pos_dao.set_pos_start("long", last, start_sz, now)
        pos_dao.add_pos_log("long", "buy", last, 0, start_sz, 1, now)
        log.info("开多 @%s sz=%s df_score=%+d", last, start_sz, df_score)
        acts.append({"action": "open_long", "last": last, "sz": start_sz})
    else:
        # ---- 持多：止盈 / 加仓 ----
        if float(last) > avg:
            if signal_dao.select_signal(2, time_end) and \
               pos_math.take_profit(avg, last, "long",
                                    strat.get("take_profit_long", 1.001)):
                sz = pos_long[4]
                pos_dao.set_pos_start("long", 0, 0, now)
                pos_dao.add_pos_log("long", "sell", last, avg, sz, 2, now)
                log.info("止盈平多 @%s 均价=%s sz=%s", last, avg, sz)
                acts.append({"action": "close_long", "last": last, "avg": avg})
        else:
            acts += _add_or_stop("long", pos_long, last, gap_rule, strat, now)
    return acts


def _handle_short(pos_short, last, last_100, last_1000, pos_ok, time_end,
                  day_low, buffer, start_sz, gap_rule, strat, now):
    acts = []
    in_pos = pos_short and pos_short[3] and float(pos_short[3]) != 0
    avg = float(pos_short[3]) if pos_short else 0

    if not in_pos:
        # ---- 开空闸门（尾数镜像：百位≠0，千位≠0且≠9）----
        if last_100 == 0 or last_1000 == 0 or last_1000 == 9:
            return acts
        if pos_ok not in (2, 3):
            return acts
        sig = signal_dao.select_signal(3, time_end)
        if not sig:
            return acts
        s24, s1 = get_situation()
        if s24 not in (0, 2) or s1 not in (0, 2):
            return acts
        if (float(last) - float(day_low)) <= buffer:
            log.info("当前价在 24h 低点缓冲内，跳过开空")
            return acts
        # ── 方向过滤器 ──
        df_ok, df_score, _ = direction_filter.check_direction("short")
        if not df_ok:
            log.info("上行趋势，禁止开空（score=%+d）@%s", df_score, last)
            return acts
        # ── 恐慌贪婪指数过滤 ──
        fng_ok, fng_reason = fng_filter.check_open("short")
        if not fng_ok:
            log.info("市场情绪高涨，禁止开空：%s @%s", fng_reason, last)
            return acts
        pos_dao.set_pos_start("short", last, start_sz, now)
        pos_dao.add_pos_log("short", "sell", last, 0, start_sz, 3, now)
        log.info("开空 @%s sz=%s df_score=%+d", last, start_sz, df_score)
        acts.append({"action": "open_short", "last": last, "sz": start_sz})
    else:
        if float(last) < avg:
            if signal_dao.select_signal(4, time_end) and \
               pos_math.take_profit(avg, last, "short",
                                    tp_short=strat.get("take_profit_short", 0.999)):
                sz = pos_short[4]
                pos_dao.set_pos_start("short", 0, 0, now)
                pos_dao.add_pos_log("short", "buy", last, avg, sz, 4, now)
                log.info("止盈平空 @%s 均价=%s sz=%s", last, avg, sz)
                acts.append({"action": "close_short", "last": last, "avg": avg})
        else:
            acts += _add_or_stop("short", pos_short, last, gap_rule, strat, now)
    return acts


def _add_or_stop(side, pos, last, gap_rule, strat, now):
    """亏损分支：gap 极端行情止损，否则马丁加仓。"""
    acts = []
    # 止损：多头遇暴跌(2)、空头遇暴涨(1)
    if (side == "long" and gap_rule == 2) or (side == "short" and gap_rule == 1):
        sz = pos[4]
        avg = float(pos[3])
        close_side = "sell" if side == "long" else "buy"
        ptype = 2 if side == "long" else 4
        pos_dao.set_pos_start(side, 0, 0, now)
        pos_dao.add_pos_log(side, close_side, last, avg, sz, ptype, now)
        log.info("last_gap 止损平%s @%s 均价=%s", side, last, avg)
        # 止损后翻转方向许可（复刻 mark_rule）
        _flip_pos_ok(side)
        acts.append({"action": "stop_" + side, "last": last})
        return acts

    # 加仓总开关
    if not strat.get("add_pos_enabled", True):
        return acts

    # 加仓次数上限：从当前仓位大小推算已加仓次数
    tcfg = config.get("trade")
    start_sz  = int(tcfg.get("start_sz", 3))
    add_sz    = int(strat.get("add_pos_sz", 3))
    max_times = int(strat.get("add_pos_max_times", 3))
    current_sz  = int(pos[4])
    add_count   = (current_sz - start_sz) // max(1, add_sz)
    if add_count >= max_times:
        log.info("已达最大加仓次数 %d/%d，跳过加仓 side=%s", add_count, max_times, side)
        return acts

    # 马丁加仓
    pos_start = float(pos[2])
    if pos_math.add_pos_trigger(pos_start, last, strat.get("add_pos_gap", 10), side):
        # 加仓方向过滤（受 direction_filter.apply_to_add 开关控制）
        df_cfg = config.get("direction_filter") or {}
        if df_cfg.get("apply_to_add", False):
            df_ok, df_score, _ = direction_filter.check_direction(side)
            if not df_ok:
                log.info("加仓被方向研判器拒绝 side=%s score=%+d @%s", side, df_score, last)
                return acts
        new_avg, new_sz = pos_math.new_avg_price(pos[3], pos[4], last, add_sz)
        pos_dao.set_pos(side, new_avg, new_sz, now)
        order_side = "buy" if side == "long" else "sell"
        ptype = 1 if side == "long" else 3
        pos_dao.add_pos_log(side, order_side, last, new_avg, add_sz, ptype, now)
        log.info("加仓 %s @%s 新均价=%s 新数量=%s（第%d次）",
                 side, last, new_avg, new_sz, add_count + 1)
        acts.append({"action": "add_" + side, "last": last, "avg": new_avg, "sz": new_sz})
    return acts


def _flip_pos_ok(stopped_side):
    """止损后翻转方向许可：止多->只空，止空->只多（复刻 mark_rule）。"""
    cur = pos_dao.get_pos_ok()
    if cur == 3:
        pos_dao.set_pos_ok(2 if stopped_side == "long" else 1)
