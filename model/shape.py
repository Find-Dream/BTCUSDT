"""形状状态码（复刻老项目 model_ma_spot.py 与 model_ma_line.py）。

阈值默认为老项目常量（点形状 band_10=10 / band_20=20，线形状 band=10），
可从 conf/config.yaml -> strategy 覆盖，供参数页调节。

点形状 ma_spot：描述 M5/M10/M20 三线的排列关系
    100=三线粘合(震荡) 500=多头排列(m5>m10>m20) 600=空头排列(m20>m10>m5)
    2xx=10 带内过渡  3xx=20 带内过渡  4xx=交叉过渡

线形状 ma_line：描述某条 MA 线的斜率/走向（由当前/前1/前2 三点采样）
    500=持续上行 600=持续下行 300=走平 1xx/2xx=拐点
"""


def model_ma_spot(masopt, band_10=10, band_20=20):
    """点形状：M5/M10/M20 排列关系 -> 状态码。"""
    m5 = masopt["m5"]
    m10 = masopt["m10"]
    m20 = masopt["m20"]

    if abs(m5 - m10) < band_10 and abs(m5 - m20) < band_10:
        return 100
    elif abs(m5 - m10) < band_10 and abs(m10 - m20) < band_10:
        return 100
    elif abs(m5 - m20) < band_10 and abs(m10 - m20) < band_10:
        return 100
    elif (abs(m10 - m20) < band_10) and (m5 > m10):
        return 211
    elif (abs(m10 - m20) < band_10) and (m5 < m10):
        return 212
    elif (abs(m5 - m20) < band_10) and (m10 > m5):
        return 221
    elif (abs(m5 - m20) < band_10) and (m10 < m5):
        return 222
    elif (abs(m5 - m10) < band_10) and (m20 > m10):
        return 231
    elif (abs(m5 - m10) < band_10) and (m20 < m10):
        return 232
    elif abs(m5 - m10) < band_20 and abs(m5 - m20) < band_20:
        return 300
    elif abs(m5 - m10) < band_20 and abs(m10 - m20) < band_20:
        return 300
    elif abs(m5 - m20) < band_20 and abs(m10 - m20) < band_20:
        return 300
    elif (abs(m10 - m20) < band_20) and (m5 > m10):
        return 311
    elif (abs(m10 - m20) < band_20) and (m5 < m10):
        return 312
    elif (abs(m5 - m20) < band_20) and (m10 > m5):
        return 321
    elif (abs(m5 - m20) < band_20) and (m10 < m5):
        return 322
    elif (abs(m5 - m10) < band_20) and (m20 > m10):
        return 331
    elif (abs(m5 - m10) < band_20) and (m20 < m10):
        return 332
    elif m10 > m5 > m20:
        return 411
    elif m20 > m5 > m10:
        return 412
    elif m10 > m20 > m5:
        return 421
    elif m5 > m20 > m10:
        return 422
    elif m5 > m10 > m20:
        return 500
    elif m20 > m10 > m5:
        return 600
    else:
        return 0


def model_ma_line(maline, band=10):
    """线形状：MA 线的当前/前1/前2 三点采样 -> 走向状态码。"""
    m5_1 = maline["m_1"]
    m5_2 = maline["m_2"]
    m5_3 = maline["m_3"]

    if (m5_1 < m5_2) and (abs(m5_2 - m5_3) < band):
        return 201
    elif (m5_1 < m5_2) and (m5_2 > m5_3):
        return 201
    elif (m5_1 > m5_2) and (m5_2 < m5_3):
        return 202
    elif (m5_1 > m5_2) and (abs(m5_2 - m5_3) < band):
        return 202
    elif (m5_2 > m5_3) and (abs(m5_2 - m5_1) < band):
        return 101
    elif (m5_3 > m5_2) and (abs(m5_2 - m5_1) < band):
        return 102
    elif (abs(m5_1 - m5_2) < band) and (abs(m5_2 - m5_3) < band):
        return 300
    elif m5_1 > m5_2 > m5_3:
        return 500
    elif m5_1 < m5_2 < m5_3:
        return 600
    else:
        return 0
