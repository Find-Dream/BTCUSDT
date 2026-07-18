"""OKX SDK 封装（python-okx 0.4.x）。

统一从 conf/okx_api.json 读取凭证与 flag（0=实盘 1=模拟盘）。
对外暴露：抓 K 线、下单、查账户余额、查持仓、查行情。
关键调用与异常都记日志。
"""
import okx.MarketData as MarketData
import okx.Trade as Trade
import okx.Account as Account

from bin import config
from bin.logger import get_logger

log = get_logger("okx_client")


def _creds():
    api = config.load_api()
    return (
        api.get("api_key", ""),
        api.get("secret_key", ""),
        api.get("passphrase", ""),
        str(api.get("flag", "1")),
    )


def _net():
    """从 runtime 读取代理与域名（供 SDK 连接 OKX）。"""
    rt = config.get("runtime")
    proxy = rt.get("proxy") or None
    domain = rt.get("domain") or "https://www.okx.com"
    return proxy, domain


def _market_api():
    # 公共行情无需凭证，但带上 flag / 代理 / 域名 以对齐环境
    _, _, _, flag = _creds()
    proxy, domain = _net()
    return MarketData.MarketAPI(flag=flag, domain=domain, proxy=proxy)


def _trade_api():
    key, secret, passphrase, flag = _creds()
    proxy, domain = _net()
    return Trade.TradeAPI(key, secret, passphrase, False, flag, domain=domain, proxy=proxy)


def _account_api():
    key, secret, passphrase, flag = _creds()
    proxy, domain = _net()
    return Account.AccountAPI(key, secret, passphrase, False, flag, domain=domain, proxy=proxy)


def is_live():
    """当前凭证是否指向实盘（flag=='0'）。"""
    return _creds()[3] == "0"


# ---------------- 行情 ----------------
def get_candles(inst_id, bar="1m", limit=30, after=None):
    """抓最新 K 线，返回 OKX data 数组（newest-first）。失败返回 []。

    after: 毫秒时间戳，返回早于该时间戳的 K 线（用于翻页回填）。
    """
    try:
        kwargs = dict(instId=inst_id, bar=bar, limit=str(limit))
        if after:
            kwargs["after"] = str(after)
        res = _market_api().get_candlesticks(**kwargs)
        if res.get("code") == "0":
            return res.get("data", [])
        log.error("get_candles 失败: %s", res)
        return []
    except Exception as e:
        log.error("get_candles 异常: %s", e)
        return []


def get_history_candles(inst_id, bar="1m", limit=100, after=None):
    """抓历史 K 线（get_history_candlesticks），失败返回 []。

    OKX history 端点可查更早的数据，after 同上。
    """
    try:
        kwargs = dict(instId=inst_id, bar=bar, limit=str(limit))
        if after:
            kwargs["after"] = str(after)
        res = _market_api().get_history_candlesticks(**kwargs)
        if res.get("code") == "0":
            return res.get("data", [])
        log.error("get_history_candles 失败: %s", res)
        return []
    except Exception as e:
        log.error("get_history_candles 异常: %s", e)
        return []


def get_ticker(inst_id):
    """最新行情 ticker（单条 dict）。失败返回 None。"""
    try:
        res = _market_api().get_ticker(instId=inst_id)
        if res.get("code") == "0" and res.get("data"):
            return res["data"][0]
        log.error("get_ticker 失败: %s", res)
    except Exception as e:
        log.error("get_ticker 异常: %s", e)
    return None


# ---------------- 账户 ----------------
def get_balance(ccy="USDT"):
    """查某币种可用余额（字符串数字）。失败返回 None。"""
    try:
        res = _account_api().get_account_balance(ccy=ccy)
        if res.get("code") == "0" and res.get("data"):
            details = res["data"][0].get("details", [])
            for d in details:
                if d.get("ccy") == ccy:
                    return d.get("availBal") or d.get("cashBal")
        log.error("get_balance 失败: %s", res)
    except Exception as e:
        log.error("get_balance 异常: %s", e)
    return None


def get_positions(inst_id, inst_type="SWAP"):
    """查持仓，返回 data 数组。失败返回 []。"""
    try:
        res = _account_api().get_positions(instType=inst_type, instId=inst_id)
        if res.get("code") == "0":
            return res.get("data", [])
        log.error("get_positions 失败: %s", res)
    except Exception as e:
        log.error("get_positions 异常: %s", e)
    return []


# ---------------- 交易 ----------------
def place_order(inst_id, td_mode, side, pos_side, ord_type, sz):
    """下单。返回 (ok, result)。关键操作记日志。"""
    try:
        res = _trade_api().place_order(
            instId=inst_id, tdMode=td_mode, side=side,
            posSide=pos_side, ordType=ord_type, sz=str(sz))
        ok = res.get("code") == "0"
        if ok:
            log.info("下单成功 %s %s %s sz=%s -> %s", inst_id, side, pos_side, sz, res.get("data"))
        else:
            log.error("下单失败 %s %s %s sz=%s -> %s", inst_id, side, pos_side, sz, res)
        return ok, res
    except Exception as e:
        log.error("下单异常 %s %s %s sz=%s: %s", inst_id, side, pos_side, sz, e)
        return False, {"error": str(e)}
