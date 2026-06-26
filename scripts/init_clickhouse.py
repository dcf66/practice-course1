"""初始化 ClickHouse 数据库和表结构。

本地 Docker 首次启动会自动执行 db/init/01_create_tables.sql；云 ClickHouse
没有这个入口，所以切到云实例后先运行本脚本：

    py scripts/init_clickhouse.py

脚本会读取 CLICKHOUSE_DB，并把建表 SQL 中的默认 price_index 库名替换为
.env 里的库名。可反复运行，SQL 均为 IF NOT EXISTS。
"""
import re
import sys
from pathlib import Path

from ch_client import get_client, get_db_name

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_PATH = PROJECT_ROOT / "db" / "init" / "01_create_tables.sql"


def _split_sql(sql: str) -> list[str]:
    """按分号切分本项目简单 DDL；移除注释。"""
    cleaned = []
    for line in sql.splitlines():
        # 本项目 SQL 中没有字符串字面量包含 --，可安全去掉行尾注释。
        line = line.split("--", 1)[0].rstrip()
        if not line.strip():
            continue
        cleaned.append(line)
    return [part.strip() for part in "\n".join(cleaned).split(";") if part.strip()]


def main():
    db = get_db_name()
    raw_sql = SQL_PATH.read_text(encoding="utf-8")
    sql = raw_sql.replace("price_index.", f"{db}.")
    sql = re.sub(
        r"CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+price_index",
        f"CREATE DATABASE IF NOT EXISTS {db}",
        sql,
        flags=re.IGNORECASE,
    )

    # 先连 default，避免目标库还不存在时连接失败。
    client = get_client(database="default")
    print(f"连接成功，开始初始化数据库: {db}")
    for statement in _split_sql(sql):
        first_line = statement.splitlines()[0]
        print(f"  执行: {first_line[:100]}")
        client.command(statement)

    check_client = get_client(database=db)
    rows = check_client.query(
        "SELECT name FROM system.tables WHERE database = {db:String} ORDER BY name",
        parameters={"db": db},
    ).result_rows
    print("\n初始化完成，当前表：")
    for (name,) in rows:
        print(f"  {db}.{name}")


if __name__ == "__main__":
    main()
