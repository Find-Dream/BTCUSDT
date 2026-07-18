"""仓位数学（复刻老项目 mark.py 加仓 / pos_log.py 盈亏计算）。

均包含 0.05% 单边手续费（老项目 0.0005）。
"""

FEE_RATE      = 0.0005   # 单边手续费率
CONTRACT_SIZE = 0.01     # 1 张 = 0.01 BTC（BTC-USDT-SWAP）


def new_avg_price(pos_last, pos_sz, add_last, add_sz):
    """加仓后的新均价（加权平均，复刻 mark.py）。

    pos_last_new = (pos_last*pos_sz + add_last*add_sz) / (pos_sz + add_sz)
    返回 (new_avg, new_sz)。
    """
    new_sz = int(pos_sz) + int(add_sz)
    new_avg = ((float(pos_last) * int(pos_sz)) + (float(add_last) * int(add_sz))) / new_sz
    return new_avg, new_sz


def add_pos_trigger(pos_start, last, gap_permille, side):
    """是否触发加仓（马丁）。gap_permille 为千分比阈值（老项目 pos_rule[1]）。

    多头：last < pos_start * (1 - g/1000)
    空头：last > pos_start * (1 + g/1000)
    """
    g = float(gap_permille) / 1000.0
    if side == "long":
        return float(last) < float(pos_start) * (1 - g)
    else:
        return float(last) > float(pos_start) * (1 + g)


def take_profit(pos_avg, last, side, tp_long=1.001, tp_short=0.999):
    """是否达到止盈价（复刻 mark.py：多 >均价×1.001，空 <均价×0.999）。"""
    if side == "long":
        return float(last) > float(pos_avg) * tp_long
    else:
        return float(last) < float(pos_avg) * tp_short


def profit(start_last, end_last, side, sz=1):
    """单笔平仓盈亏（含双边手续费），返回 (净收益 USDT, 收益率%)。

    毛收益 = 价差 × 张数 × CONTRACT_SIZE
    手续费 = (开仓价 + 平仓价) × FEE_RATE × 张数 × CONTRACT_SIZE
    净收益 = 毛收益 - 手续费

    多仓：price_diff = end - start
    空仓：price_diff = start - end
    """
    start_last = float(start_last)
    end_last   = float(end_last)
    sz         = int(sz)
    multiplier = sz * CONTRACT_SIZE

    price_diff = (end_last - start_last) if side == "long" else (start_last - end_last)
    gross      = price_diff * multiplier
    fee        = (start_last + end_last) * FEE_RATE * multiplier
    net        = round(gross - fee, 4)
    rate       = round(price_diff / start_last * 100, 2)
    return net, rate


def scale_size(ccy_balance, last, lever, sz_divisor):
    """把账户余额换算为下单量系数（复刻 jiaoyi.py）。

    max_sz = int(ccy * lever / last * 100)
    sz_r   = max_sz / sz_divisor
    返回 sz_r（每单位 start_sz 对应的实际张数系数）。
    """
    max_sz = int(float(ccy_balance) * float(lever) / float(last) * 100)
    return max_sz / float(sz_divisor)
