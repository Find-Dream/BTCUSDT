"""统一入口：初始化数据库 -> 启动后台调度线程 -> 启动 Flask Web。

用法：
    python3 main.py                # 启动 Web + 后台交易调度（同进程）
    python3 main.py --no-scheduler # 只启动 Web（用于纯查看）
    python3 main.py --init-db      # 只建库后退出
"""
import sys

from bin import config, scheduler
from bin.logger import get_logger
from data import db
from web.app import create_app

log = get_logger("main")


def main():
    args = sys.argv[1:]

    if "--init-db" in args:
        print("初始化数据库:", db.init_db())
        return

    db.init_db()

    if "--no-scheduler" not in args:
        scheduler.start()
    else:
        log.info("已禁用后台调度，仅启动 Web")

    rt = config.get("runtime")
    host = rt.get("web_host", "0.0.0.0")
    port = int(rt.get("web_port", 5000))
    live = "实盘" if config.get("trade", "live_enabled") else "模拟盘"
    log.info("启动 Web 服务 http://%s:%d  交易模式=%s", host, port, live)

    app = create_app()
    # 关闭 reloader，避免调度线程被 fork 两次
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
