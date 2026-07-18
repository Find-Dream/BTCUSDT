"""均线计算（复刻老项目 model_jsma.py）。

约定：k_json 为 OKX 蜡烛数组，newest-first（下标 0 = 最新一根），
每根形如 [ts, open, high, low, close, vol, volCcy, ...]，只用收盘价 close=i[4]。

- jsma      : 当前分钟的 M5 / M10 / M20（简单均值）
- jsma_3    : 当前 / 前1 / 前2 分钟的 M10（窗口 10；老项目 8月30日由 M5 改为 M10）
- jsma_3_3  : 当前 / 前1 / 前2 分钟的 M5（窗口 5；老项目由 M3 改为 M5）
"""


def _closes(k_json):
    """提取收盘价列表（float），保持 newest-first 顺序。"""
    return [float(i[4]) for i in k_json]


def jsma(k_json):
    """当前分钟的 M5 / M10 / M20 = 最近 5 / 10 / 20 根收盘价的简单均值。"""
    closes = _closes(k_json)
    m5 = sum(closes[:5]) / 5
    m10 = sum(closes[:10]) / 10
    m20 = sum(closes[:20]) / 20
    return {"m5": m5, "m10": m10, "m20": m20}


def jsma_3(k_json):
    """窗口 10 的 MA 在 当前 / 前1 / 前2 分钟的取值（用于判断线形状/斜率）。"""
    closes = _closes(k_json)
    m_1 = sum(closes[0:10]) / 10
    m_2 = sum(closes[1:11]) / 10
    m_3 = sum(closes[2:12]) / 10
    return {"m_1": m_1, "m_2": m_2, "m_3": m_3}


def jsma_3_3(k_json):
    """窗口 5 的 MA 在 当前 / 前1 / 前2 分钟的取值。"""
    closes = _closes(k_json)
    m_1 = sum(closes[0:5]) / 5
    m_2 = sum(closes[1:6]) / 5
    m_3 = sum(closes[2:7]) / 5
    return {"m_1": m_1, "m_2": m_2, "m_3": m_3}
