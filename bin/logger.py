"""统一日志：logging + 按天轮转，输出到 log/ 目录。

用法：
    from bin.logger import get_logger
    log = get_logger("trader")
    log.info("下单成功 ...")

关键操作（下单、开平仓、加仓、止损、模型晋升、命中、配置变更、API 异常）
都应通过对应模块的 logger 记录 INFO / ERROR。
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_BASE, "log")
_loggers = {}


def get_logger(name):
    """按模块名返回 logger，每个模块一个 log/<name>.log，按天轮转保留 14 天。"""
    if name in _loggers:
        return _loggers[name]

    os.makedirs(_LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # 文件：按天轮转，保留 14 天（对齐老项目 del_log 的 14 天保留）
        fh = TimedRotatingFileHandler(
            os.path.join(_LOG_DIR, name + ".log"),
            when="midnight", backupCount=14, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        # 控制台
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    _loggers[name] = logger
    return logger
