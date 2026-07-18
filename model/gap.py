"""暴涨暴跌判定（复刻老项目 mark.last_gap_for5 的纯计算部分）。

输入最近 10 个 gap（tick 间价差，newest-first）与上一状态 gap_rule_num，
输出 (gap_rule, new_gap_rule_num)：
    gap_rule    : 0=无信号 1=暴涨确认 2=暴跌确认
    new_gap_rule_num : 写回 gap_rule_num 表的最新状态（0/1）

老逻辑：连续 5 根 gap 同向超阈值(num) -> 进入准信号；其中任一超强阈值(num_b)
或连续 10 根都超阈值 -> 若上一状态已是 1 则确认(1/2)，否则置 1 待确认。
"""


def gap_rule_for5(gap_list, prev_gap_rule_num, num=30, num_b=200):
    """gap_list: 最近 10 个 gap（newest-first）。返回 (gap_rule, new_num)。"""
    g = gap_list
    if len(g) < 10:
        return 0, 0
    num2 = -num
    num2_b = -num_b

    up5 = all(g[i] > num for i in range(5))
    down5 = all(g[i] < num2 for i in range(5))

    if up5:
        strong = any(g[i] > num_b for i in range(5))
        up10 = all(g[i] > num for i in range(10))
        if strong or up10:
            if prev_gap_rule_num == 1:
                return 1, 1          # 确认暴涨
            return 0, 1              # 置位待确认
        return 0, 0
    elif down5:
        strong = any(g[i] < num2_b for i in range(5))
        down10 = all(g[i] < num2 for i in range(10))
        if strong or down10:
            if prev_gap_rule_num == 1:
                return 2, 1          # 确认暴跌
            return 0, 1
        return 0, 0
    else:
        return 0, 0
