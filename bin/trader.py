"""交易执行层（复刻老项目 jiaoyi.py 的对账下单，默认模拟盘）。

交易模式（_trade_mode）：
  live  ─ okx_api.json flag=0 + live_enabled=true + confirm_live 口令正确
           → 真实下单到 OKX 实盘账户
  paper ─ okx_api.json flag=1 + live_enabled=true + confirm_live 口令正确
           → 下单到 OKX 模拟盘账户（需在 OKX 申请模拟盘 API Key）
  sim   ─ 其余所有情况
           → 只记日志，不触达交易所

pos_log 是唯一真相来源：读取最新一条订单，缩放数量后镜像到账户。
"""
import time

from bin import config, okx_client
from bin.logger import get_logger
from data import pos_dao
from model.position import scale_size

log = get_logger("trader")

_LIVE_TOKEN = "I_KNOW_THE_RISK"


def _trade_mode():
    """返回当前交易模式字符串：'live' / 'paper' / 'sim'。

    live  ─ flag=0 且三重开关全通，真实下单到实盘账户
    paper ─ flag=1 且三重开关全通，下单到 OKX 模拟盘账户
    sim   ─ 其余情况，只记日志不触达交易所
    """
    t = config.get("trade")
    if not t.get("live_enabled", False):
        return "sim"
    if t.get("confirm_live", "") != _LIVE_TOKEN:
        return "sim"
    flag = okx_client._creds()[3]   # "0"=实盘  "1"=模拟盘
    if flag == "0":
        return "live"
    if flag == "1":
        return "paper"
    return "sim"


def live_allowed():
    """向后兼容：是否为实盘模式。"""
    return _trade_mode() == "live"


def execute_latest():
    """读取最新 pos_log 订单并执行（对账后下单或模拟）。返回结果 dict。"""
    order = pos_dao.latest_pos_log()
    if not order:
        return {"status": "no_order"}

    _id, side, side_1, last, pos_last, sz, postype, uptime = order

    # 订单时效检查（老项目 11 秒）
    ttl = config.get("trade", "order_ttl", 11)
    if time.time() > uptime + ttl:
        log.info("订单 #%s 超时(%.1fs)，错过最佳交易时间，跳过", _id, time.time() - uptime)
        return {"status": "expired", "id": _id}

    rt = config.get("runtime")
    t  = config.get("trade")
    inst_id  = rt.get("inst_id", "BTC-USDT-SWAP")
    pos_side = side             # long / short
    ord_side = side_1           # buy / sell
    td_mode  = t.get("td_mode",  "cross")
    ord_type = t.get("ord_type", "market")

    mode = _trade_mode()

    # ── 纯本地模拟：不调用 OKX 接口 ──
    if mode == "sim":
        log.info("[模拟成交] #%s %s %s pos=%s sz=%s @%s",
                 _id, ord_side, pos_side, postype, sz, last)
        return {"status": "simulated", "id": _id, "side": ord_side,
                "posSide": pos_side, "sz": int(sz), "last": last}

    # ── 实盘 / OKX 模拟盘：均调用 OKX 下单接口 ──
    real_sz = _real_size(sz, last, t)
    ok, res = okx_client.place_order(inst_id, td_mode, ord_side, pos_side, ord_type, real_sz)
    label   = "实盘" if mode == "live" else "OKX模拟盘"
    if ok:
        log.info("[%s] 下单成功 #%s %s %s sz=%s @%s",
                 label, _id, ord_side, pos_side, real_sz, last)
    else:
        log.error("[%s] 下单失败 #%s -> %s", label, _id, res)
    return {"status": mode if ok else "failed", "id": _id, "result": res}


def _real_size(sz, last, t):
    """按账户余额缩放下单量；取不到余额时回退为原始 sz。"""
    try:
        bal = okx_client.get_balance("USDT")
        if bal is None:
            return int(sz)
        sz_r = scale_size(bal, last, t.get("lever", 1), t.get("sz_divisor", 15))
        return max(1, int(int(sz) * sz_r))
    except Exception as e:
        log.error("数量缩放失败，回退原始 sz: %s", e)
        return int(sz)
