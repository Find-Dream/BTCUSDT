"""Web 路由：首页 K 线图、参数调节页、模型管理页、回测页、日志页，及对应 JSON 接口。"""
import os
import time

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, Response, stream_with_context

# 日志目录（项目根目录下的 log/）
_LOG_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
_LOG_NAMES = ["main", "mark", "monitor", "trader", "kline",
              "web", "scheduler", "okx_client", "backtest", "autostudy"]

from bin import config, kline as kline_bin, autostudy, monitor
from bin import backtest as backtest_bin
from bin.logger import get_logger
from data import kline_dao, models_dao, pos_dao, signal_dao
from model.fingerprint import fingerprint, FIELDS
from model.ma import jsma
from model.position import profit

log = get_logger("web")
bp = Blueprint("main", __name__)


# ==================== 页面 ====================
@bp.route("/")
def index():
    """首页：K 线图。"""
    return render_template("index.html")


@bp.route("/settings")
def settings():
    """参数调节页。"""
    return render_template("settings.html", cfg=config.load())


@bp.route("/models")
def models():
    """模型管理页。"""
    return render_template("models.html")


@bp.route("/backtest")
def backtest():
    """回测页。"""
    return render_template("backtest.html")


@bp.route("/logs")
def logs():
    """日志查看页。"""
    return render_template("logs.html", log_names=_LOG_NAMES)


# ==================== 日志流接口 ====================
@bp.route("/api/logs/stream")
def api_logs_stream():
    """SSE：先推最近 100 行历史，再实时 tail 新增内容。

    参数：
        name : 日志名称（不含 .log，须在 _LOG_NAMES 白名单内）
    事件格式：
        data: {"line": "..."}
    """
    import json as _json

    name = request.args.get("name", "main")
    if name not in _LOG_NAMES:
        name = "main"
    log_path = os.path.join(_LOG_DIR, name + ".log")

    def generate():
        # 打开文件（文件不存在时给提示行后退出）
        try:
            f = open(log_path, "r", encoding="utf-8", errors="replace")
        except FileNotFoundError:
            yield "data: " + _json.dumps({"line": f"[{name}.log 尚未创建]"}) + "\n\n"
            return

        try:
            # ── 历史：最近 100 行 ──
            raw = f.readlines()
            for line in (raw[-100:] if len(raw) > 100 else raw):
                stripped = line.rstrip()
                if stripped:
                    yield "data: " + _json.dumps({"line": stripped}) + "\n\n"

            # ── 实时 tail：循环 readline ──
            while True:
                line = f.readline()
                if line:
                    stripped = line.rstrip()
                    if stripped:
                        yield "data: " + _json.dumps({"line": stripped}) + "\n\n"
                else:
                    # 检测日志轮转（当前偏移超出文件大小）
                    try:
                        cur_size = os.path.getsize(log_path)
                    except OSError:
                        cur_size = 0
                    if f.tell() > cur_size:
                        f.close()
                        try:
                            f = open(log_path, "r", encoding="utf-8", errors="replace")
                        except FileNotFoundError:
                            break
                    time.sleep(0.3)
                    yield ": keepalive\n\n"   # 防超时断连
        except GeneratorExit:
            pass
        finally:
            try:
                f.close()
            except Exception:
                pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 回测接口 ====================
@bp.route("/api/backtest", methods=["POST"])
def api_backtest():
    """执行历史回测，以 SSE 流式推送日志，最后推送完整结果。

    事件格式（text/event-stream）：
        data: {"type":"log",    "msg":"..."}
        data: {"type":"result", "data":{...}}
        data: {"type":"error",  "msg":"..."}
    """
    import json as _json
    import queue
    import threading
    import datetime

    payload   = request.get_json(force=True)
    bar       = payload.get("bar", "1m")
    table     = "model_1m"
    start_str = payload.get("start", "")
    end_str   = payload.get("end",   "")

    # ---- 参数校验（在主线程里，出错直接返回普通 JSON）----
    if bar not in ("1m", "5m", "15m"):
        return jsonify({"error": "不支持的周期"})

    def _parse(s):
        # 前端可直接传 Unix 秒级整数时间戳
        if isinstance(s, (int, float)):
            return int(s)
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return int(datetime.datetime.strptime(s, fmt).timestamp())
            except ValueError:
                pass
        raise ValueError("无法解析时间: " + s)

    try:
        start_ts = _parse(start_str)
        end_ts   = _parse(end_str)
    except Exception as e:
        return jsonify({"error": "时间格式错误: " + str(e)})

    if end_ts <= start_ts:
        return jsonify({"error": "结束时间必须晚于开始时间"})

    # ---- SSE 流式推送 ----
    q = queue.Queue()

    def log_cb(msg):
        q.put({"type": "log", "msg": msg})

    def progress_cb(pct):
        q.put({"type": "progress", "pct": pct})

    def worker():
        try:
            result = backtest_bin.run(bar, start_ts, end_ts, table=table,
                                      log_cb=log_cb, progress_cb=progress_cb)
            if "error" in result:
                q.put({"type": "error", "msg": result["error"]})
            else:
                q.put({"type": "result", "data": result})
        except Exception as e:
            log.error("回测异常: %s", e)
            q.put({"type": "error", "msg": str(e)})
        finally:
            q.put(None)  # 结束哨兵

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield "data: " + _json.dumps(item, ensure_ascii=False) + "\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== K 线接口 ====================
@bp.route("/api/kline")
def api_kline():
    """返回 K 线 + MA5/10/20，直接从 OKX 实时拉取，不写库。

    参数：
        bar   : 1m / 5m / 15m（默认 1m）
        start : 开始秒级时间戳（缺省则 end-86400）
        end   : 结束秒级时间戳（缺省则当前时间）
    """
    bar = request.args.get("bar", "1m")
    if bar not in ("1m", "5m", "15m"):
        bar = "1m"

    now = int(time.time())
    end_ts   = request.args.get("end",   default=now,          type=int)
    start_ts = request.args.get("start", default=end_ts-86400, type=int)

    # 直接从 OKX 拉取，不落库
    raw = kline_bin.fetch_range(bar, start_ts, end_ts)  # oldest-first

    candles, times, tslist, mas, volumes = [], [], [], {"m5": [], "m10": [], "m20": []}, []
    closes = [float(r[4]) for r in raw]   # OKX r[4] = close

    for idx, r in enumerate(raw):
        ts = int(r[0]) // 1000            # OKX r[0] = ts_ms
        times.append(time.strftime("%m-%d %H:%M", time.localtime(ts)))
        tslist.append(ts)
        # ECharts candlestick: [open, close, low, high]
        candles.append([float(r[1]), float(r[4]), float(r[3]), float(r[2])])
        mas["m5"].append(_ma(closes, idx, 5))
        mas["m10"].append(_ma(closes, idx, 10))
        mas["m20"].append(_ma(closes, idx, 20))
        volumes.append(float(r[5]))       # OKX r[5] = vol（基础货币成交量）

    return jsonify({"times": times, "ts": tslist, "candles": candles, "ma": mas, "volumes": volumes})


def _ma(closes, idx, n):
    seg = closes[idx - n + 1: idx + 1]
    if len(seg) < n:
        return None
    return round(sum(seg) / n, 2)


@bp.route("/api/signals")
def api_signals():
    """最近命中信号，供首页图上标注。"""
    rows = signal_dao.list_signals(limit=100)
    data = [{"model_id": r[1], "model_type": r[2], "last": r[3],
             "time": time.strftime("%m-%d %H:%M", time.localtime(r[4]))} for r in rows]
    return jsonify(data)


@bp.route("/api/status")
def api_status():
    """系统状态摘要：持仓、方向许可、交易模式。"""
    pos_long = pos_dao.get_pos("long")
    pos_short = pos_dao.get_pos("short")
    return jsonify({
        "live": bool(config.get("trade", "live_enabled")),
        "pos_ok": pos_dao.get_pos_ok(),
        "long": {"avg": pos_long[3] if pos_long else 0, "sz": pos_long[4] if pos_long else 0},
        "short": {"avg": pos_short[3] if pos_short else 0, "sz": pos_short[4] if pos_short else 0},
    })


# ==================== 参数接口 ====================
@bp.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(config.load())
    # POST：合并保存（Web 表单提交，节区/键值热更新）
    incoming = request.get_json(force=True)
    cfg = config.load()
    for section, kv in incoming.items():
        if section in cfg and isinstance(cfg[section], dict):
            cfg[section].update(kv)
        else:
            cfg[section] = kv
    config.save(cfg)
    log.info("配置已更新: %s", list(incoming.keys()))
    return jsonify({"ok": True, "config": cfg})


# ==================== 模型接口 ====================
@bp.route("/api/models")
def api_models():
    rows = models_dao.list_models("model_1m", limit=300)
    cols = ["id", "type"] + list(__import__("model.fingerprint", fromlist=["FIELDS"]).FIELDS) + ["uptime"]
    data = [dict(zip(cols, r)) for r in rows]
    return jsonify(data)


@bp.route("/api/models/delete", methods=["POST"])
def api_models_delete():
    payload = request.get_json(force=True)
    models_dao.delete_model("model_1m", int(payload["id"]))
    monitor.reload_cache("model_1m")
    log.info("删除模型 model_1m#%s", payload["id"])
    return jsonify({"ok": True})


@bp.route("/api/models/promote", methods=["POST"])
def api_models_promote():
    """晋升某时间节点的图形为交易模型（手动学习）。

    请求体：{ "type": 1, "ts": 1784250060, "bar": "1m" }
      - type：模型类型 1开多/2平多/3开空/4平空
      - ts  ：K 线秒级时间戳（在 K 线图上点选得到）；缺省则用最新一根
      - bar ：K 线周期（仅用于拉取对应粒度的 K 线，模型一律写入 model_1m）
    """
    from model.fingerprint import fingerprint
    payload = request.get_json(force=True)
    model_type = int(payload.get("type", 1))
    ts = payload.get("ts")
    bar = payload.get("bar", "1m")
    table = "model_1m"
    strat = config.get("strategy")

    # 取指纹计算所需的 K 线窗口（直接从 OKX 拉，不依赖 DB）
    bar_sec = {"1m": 60, "5m": 300, "15m": 900}.get(bar, 60)
    if ts:
        ts_int = int(ts)
        raw = kline_bin.fetch_range(bar, ts_int - 30 * bar_sec, ts_int)
        # newest-first for fingerprint
        jg = list(reversed([[int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                              float(r[4]), float(r[5]), float(r[6])] for r in raw]))
        when = time.strftime("%m-%d %H:%M", time.localtime(ts_int))
    else:
        jg = kline_bin.fetch(bar=bar, save=False)
        when = "最新"

    if not jg or len(jg) < 25:
        return jsonify({"ok": False, "msg": "该时间点 K 线数据不足（需约 25 根历史），换一个更晚的时间点"})

    codes = fingerprint(jg, strat.get("ma_spot_band_10", 10),
                        strat.get("ma_spot_band_20", 20), strat.get("ma_line_band", 10))
    mid = autostudy.promote(codes, model_type, table=table)
    if mid is None:
        return jsonify({"ok": False, "msg": "该图形已存在于模型库（去重）", "codes": codes})
    monitor.reload_cache(table)   # 刷新内存匹配缓存
    return jsonify({"ok": True, "id": mid, "codes": codes, "when": when, "table": table})


@bp.route("/api/pnl")
def api_pnl():
    """模拟持仓盈亏流水（配对开平仓，供模型管理页）。"""
    rows = pos_dao.list_pos_log(limit=500)
    # rows newest-first -> oldest-first 便于配对
    rows = list(reversed(rows))
    trades = []
    opens = {"long": None, "short": None}
    for r in rows:
        _id, side, side_1, last, pos_last, sz, postype, uptime = r
        is_open = (side == "long" and side_1 == "buy") or (side == "short" and side_1 == "sell")
        if is_open:
            opens[side] = r
        else:
            o = opens.get(side)
            if o:
                shouyi, lv = profit(o[3], last, side, sz=o[5])
                trades.append({"side": side, "open": o[3], "close": last,
                               "profit": shouyi, "rate": lv,
                               "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(uptime))})
                opens[side] = None
    total = round(sum(t["profit"] for t in trades), 2)
    return jsonify({"trades": list(reversed(trades)), "total": total})
