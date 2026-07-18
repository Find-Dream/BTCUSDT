"""15 码指纹（复刻老项目 monitor.addmodel + 滑窗组装逻辑）。

一个时间窗口经 addmodel() 得到 3 个状态码 (点形状, 5线形状, 3线形状)。
主循环沿最近 5 分钟滑动窗口，拼成 15 维分类指纹：
    [spot_1,m5_1,m3_1, spot_2,m5_2,m3_2, ... spot_5,m5_5,m3_5]
前 9 码用于 3 分钟匹配，全 15 码用于 5 分钟（更强）匹配。

模型类型 model_type：1=开多 2=平多 3=开空 4=平空 0=study(原始采样)
"""
from model.ma import jsma, jsma_3, jsma_3_3
from model.shape import model_ma_spot, model_ma_line

# 15 码字段名，与数据库 model_* 表列一一对应
FIELDS = [
    "spot_1", "m5_1", "m3_1",
    "spot_2", "m5_2", "m3_2",
    "spot_3", "m5_3", "m3_3",
    "spot_4", "m5_4", "m3_4",
    "spot_5", "m5_5", "m3_5",
]


def addmodel(k_window, band_10=10, band_20=20, line_band=10):
    """单个窗口 -> (点形状, 5线形状, 3线形状) 三元组。"""
    maspot_a = model_ma_spot(jsma(k_window), band_10, band_20)
    maline_5 = model_ma_line(jsma_3(k_window), line_band)
    maline_3 = model_ma_line(jsma_3_3(k_window), line_band)
    return maspot_a, maline_5, maline_3


def fingerprint(jg_list, band_10=10, band_20=20, line_band=10):
    """由 K 线列表（newest-first，>=约 25 根）生成 15 码指纹。

    复刻老项目：取 jg_list[0:-1], [1:-1], [2:-1], [3:-1], [4:-1] 五个窗口。
    """
    windows = [
        jg_list[0:-1],
        jg_list[1:-1],
        jg_list[2:-1],
        jg_list[3:-1],
        jg_list[4:-1],
    ]
    codes = []
    for w in windows:
        for code in addmodel(w, band_10, band_20, line_band):
            codes.append(code)
    return codes  # 长度 15


def time_window(jg_list):
    """当前 K 线的时间窗口 [start, end]（秒），复刻老项目算法。"""
    ts0 = int(jg_list[0][0])
    ts1 = int(jg_list[1][0])
    start = int(ts0 / 1000)
    end = int((ts0 + ts0 - ts1) / 1000)
    return start, end
