"""宏观形势判定（复刻老项目 mark.situation 的纯计算部分）。

输入 1h / 24h / 72h 的均价和当前价，输出 (situation_24h_id, situation_1h_id)：
    situation_24h_id : 1=上行 2=下行 0=走平
    situation_1h_id  : 1=上行 2=下行 0=走平 3=极端行情
含义（交易闸门用）：0=全放行 1=禁空 2=禁多 3=禁止
"""


def situation(avg_1h, avg_24h, avg_72h, last,
              extreme=1500, pct_1h=0.01):
    """根据均价关系计算宏观形势状态码。"""
    # 24 小时趋势：24h 均价 vs 72h 均价
    if (avg_24h - avg_72h) > 0:
        situation_24h_id = 1
    elif (avg_24h - avg_72h) < 0:
        situation_24h_id = 2
    else:
        situation_24h_id = 0

    # 1 小时趋势：需超过 24h 均价的 pct_1h（默认 1%）
    if (avg_1h - avg_24h) > 0 and abs(avg_1h - avg_24h) > avg_24h * pct_1h:
        situation_1h_id = 1
    elif (avg_1h - avg_24h) < 0 and abs(avg_1h - avg_24h) > avg_24h * pct_1h:
        situation_1h_id = 2
    else:
        situation_1h_id = 0

    # 极端行情：当前价偏离 24h 均价超过阈值
    if abs(last - avg_24h) > extreme:
        situation_1h_id = 3

    return situation_24h_id, situation_1h_id
