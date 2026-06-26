"""ClickHouse 连接配置：从 .env 读取，返回一个可用的 client。

其他脚本只要 `from ch_client import get_client` 即可，
本地/云切换只需改 .env 里的 CLICKHOUSE_* 配置，代码无需改动。

直接运行本文件可测试连接并打印当前库里的表。
"""
import os
import sys
from pathlib import Path

import clickhouse_connect
from dotenv import load_dotenv

# Windows 控制台可能不是 UTF-8，强制让 print 中文不报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_db_name() -> str:
    """返回业务数据库名。"""
    return os.getenv("CLICKHOUSE_DB", "price_index")


def table(name: str) -> str:
    """返回带数据库名前缀的表名。"""
    return f"{get_db_name()}.{name}"


def get_client(database: str | None = None):
    """根据 .env 配置返回一个 ClickHouse client（HTTP 接口）。"""
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    password = os.getenv("CLICKHOUSE_PASSWORD", "")
    db = database if database is not None else get_db_name()
    secure = _as_bool(os.getenv("CLICKHOUSE_SECURE"), default=False)
    verify = _as_bool(os.getenv("CLICKHOUSE_VERIFY"), default=True)

    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password,
        database=db,
        secure=secure,
        verify=verify,
    )


if __name__ == "__main__":
    client = get_client()
    version = client.server_version
    db = get_db_name()
    print(f"连接成功！ClickHouse 版本 = {version}，数据库 = {db}")
    print("当前库里的表：")
    rows = client.query(
        "SELECT name, total_rows FROM system.tables "
        "WHERE database = {db:String} ORDER BY name",
        parameters={"db": db},
    ).result_rows
    if not rows:
        print("  （还没有任何表）")
    for name, total_rows in rows:
        print(f"  {name:24}  行数={total_rows}")
