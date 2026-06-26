"""把 data/ 里的 CSV 清洗后灌入 ClickHouse。

清洗要点：
  - 所有 CSV 都是 GBK 编码（中文），统一用 encoding='gbk' 读取。
  - categories.csv 里的 'null' 文本转成真正的空值（NULL）。
  - 每日价格文件一天内同一 SKU 有多个报价 —— 用「杰文斯几何平均」
    （exp(mean(log(price)))）合并成一个价，能抹平个别商家的极端报价。
  - 灌库前先 TRUNCATE 目标表，所以本脚本可反复运行，不会重复插入。

用法：
    py scripts/load_to_clickhouse.py                # 灌全部（1095 个每日文件）
    py scripts/load_to_clickhouse.py --limit 5      # 只灌前 5 个每日文件（先测试）
    py scripts/load_to_clickhouse.py --skip-daily   # 只灌两张维表，不灌每日明细
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ch_client import get_client, table

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DAILY_DIR = DATA_DIR / "daily_price"
DATE_RE = re.compile(r"daily_prices_(\d{8})\.csv$")
ENCODING = "gbk"  # 数据是 GBK 编码


def load_categories(client):
    """类目维表：data/categories.csv -> dim_category"""
    path = DATA_DIR / "categories.csv"
    df = pd.read_csv(path, encoding=ENCODING, na_values=["null", "NULL", ""])
    # 列: category, category_id, hierarchy, weight, price, parent
    target = table("dim_category")
    client.command(f"TRUNCATE TABLE {target}")

    rows = []
    for r in df.itertuples(index=False):
        price = None if pd.isna(r.price) else float(r.price)
        parent = None if pd.isna(r.parent) else int(r.parent)
        rows.append([
            str(r.category),
            int(r.category_id),
            int(r.hierarchy),
            float(r.weight),
            price,
            parent,
        ])
    client.insert(
        target,
        rows,
        column_names=["category_name", "category_id", "hierarchy",
                      "weight", "price", "parent"],
    )
    print(f"[dim_category]  灌入 {len(rows)} 行")


def load_products(client):
    """商品维表：data/products.csv -> dim_product"""
    path = DATA_DIR / "products.csv"
    df = pd.read_csv(path, encoding=ENCODING, na_values=["null", "NULL", ""])
    # 列: product_id, category_id, name, weight, price, change_count
    df = df.dropna(subset=["product_id", "category_id", "price"])
    out = pd.DataFrame({
        "product_id": df["product_id"].astype("int64"),
        "category_id": df["category_id"].astype("int64"),
        "name": df["name"].astype(str),
        "weight": df["weight"].astype(float),
        "base_price": df["price"].astype(float),
        "change_count": df["change_count"].fillna(0).astype("int64"),
    })
    target = table("dim_product")
    client.command(f"TRUNCATE TABLE {target}")
    client.insert_df(target, out)
    print(f"[dim_product]   灌入 {len(out)} 行")


def clean_daily_file(path: Path, dt) -> pd.DataFrame:
    """读单个每日文件，按 SKU 做几何平均去重，返回待插入的 DataFrame。"""
    df = pd.read_csv(path, encoding=ENCODING, na_values=["null", "NULL", ""])
    # 列: product_id, category_id, name, price, change_date
    df = df.dropna(subset=["product_id", "price"])
    df = df[df["price"] > 0]  # 几何平均要求价格为正
    if df.empty:
        return df

    # 杰文斯几何平均：同一 product_id 的多个报价取 exp(mean(ln(price)))
    df["log_price"] = np.log(df["price"].astype(float))
    grouped = df.groupby("product_id", as_index=False).agg(
        category_id=("category_id", "first"),
        name=("name", "first"),
        log_price=("log_price", "mean"),
    )
    out = pd.DataFrame({
        "dt": dt,
        "product_id": grouped["product_id"].astype("int64"),
        "category_id": grouped["category_id"].astype("int64"),
        "name": grouped["name"].astype(str),
        "price": np.exp(grouped["log_price"]).round(4),
    })
    return out


def load_daily(client, limit=None):
    """每日明细：data/daily_price/*.csv -> fact_sku_daily_price"""
    files = sorted(DAILY_DIR.glob("daily_prices_*.csv"))
    if limit is not None:
        files = files[:limit]

    target = table("fact_sku_daily_price")
    client.command(f"TRUNCATE TABLE {target}")
    total = len(files)
    print(f"\n[fact_sku_daily_price] 开始灌入 {total} 个每日文件...")

    total_rows = 0
    for i, path in enumerate(files, 1):
        m = DATE_RE.search(path.name)
        if not m:
            print(f"  [跳过] 文件名不符合规则: {path.name}")
            continue
        s = m.group(1)
        dt = pd.Timestamp(f"{s[0:4]}-{s[4:6]}-{s[6:8]}").date()
        out = clean_daily_file(path, dt)
        if out.empty:
            continue
        client.insert_df(target, out)
        total_rows += len(out)
        if i % 20 == 0 or i == total:
            print(f"  进度 {i}/{total}  累计灌入 {total_rows} 行")

    print(f"[fact_sku_daily_price] 完成，共灌入 {total_rows} 行")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="只灌前 N 个每日文件（测试用）")
    parser.add_argument("--skip-daily", action="store_true",
                        help="只灌两张维表，不灌每日明细")
    args = parser.parse_args()

    client = get_client()
    print("连接 ClickHouse 成功，开始灌数据...\n")

    load_categories(client)
    load_products(client)
    if not args.skip_daily:
        load_daily(client, limit=args.limit)

    # 汇总每张表的行数
    print("\n=== 各表当前行数 ===")
    for t in ["dim_category", "dim_product", "fact_sku_daily_price"]:
        n = client.query(f"SELECT count() FROM {table(t)}").result_rows[0][0]
        print(f"  {t:24} {n}")


if __name__ == "__main__":
    main()
