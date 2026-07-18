"""配置加载与热更新。

- config.yaml：策略/交易/运行参数，Web 参数页可读写，支持热更新。
- okx_api.json：API 凭证（不入库、不提交），仅本地读取。
"""
import os
import json
import threading

import yaml

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_BASE, "conf", "config.yaml")
API_PATH = os.path.join(_BASE, "conf", "okx_api.json")

_lock = threading.RLock()
_cache = None


def base_dir():
    """项目根目录绝对路径。"""
    return _BASE


def abspath(rel):
    """把 config 中的相对路径转为基于项目根目录的绝对路径。"""
    if os.path.isabs(rel):
        return rel
    return os.path.join(_BASE, rel)


def load(force=False):
    """读取配置（带缓存）。force=True 时强制重新读盘。"""
    global _cache
    with _lock:
        if _cache is None or force:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _cache = yaml.safe_load(f)
        return _cache


def reload():
    """强制重新加载配置，返回最新配置。"""
    return load(force=True)


def save(cfg):
    """把配置写回 config.yaml 并刷新缓存（供 Web 参数页调用）。"""
    global _cache
    with _lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        _cache = cfg
        return _cache


def get(section, key=None, default=None):
    """便捷读取：get('strategy', 'gap_num')。"""
    cfg = load()
    sec = cfg.get(section, {})
    if key is None:
        return sec
    return sec.get(key, default)


def load_api():
    """读取 OKX 凭证；文件缺失时回退到示例（模拟盘 flag=1），并提示。"""
    path = API_PATH
    if not os.path.exists(path):
        example = API_PATH.replace("okx_api.json", "okx_api.example.json")
        if os.path.exists(example):
            path = example
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())
