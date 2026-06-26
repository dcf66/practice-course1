"""从 OSS raw/ 区读取 CSV，清洗后灌入 ClickHouse。

该脚本用于 GitHub Actions 或没有本地 data/ 目录的环境。它复用本地
load_to_clickhouse.py 的清洗口径：
  - CSV 使用 GBK 编码读取。
  - 类目与商品维表先 TRUNCATE 再写入。
  - 每日价格同一 SKU 多报价用杰文斯几何平均去重。

用法：
    py scripts/load_from_oss_to_clickhouse.py --limit 5
    py scripts/load_from_oss_to_clickhouse.py --full
"""
import argparse
import io
import re
import sys

import numpy as np
import oss2
import pandas as pd

from ch_client import get_client, table
from oss_client import get_bucket

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ENCODING = "gbk"
DATE_RE = re.compile(r"raw/daily_price/dt=(\d{8})/daily_prices_\d{8}\.csv$")


def read_csv_object(bucket: oss2.Bucket, key: str) -> pd.DataFrame:
    data = bucket.get_object(key).read()
    return pd.read_csv(io.BytesIO(data), encoding=ENCODING, na_values=["null", "NULL", ""])


def load_categories(client, bucket):
    df = read_csv_object(bucket, "raw/categories.csv")
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
        column_names=["category_name", "category_id", "hierarchy", "weight", "price", "parent"],
    )
    print(f"[dim_category]  灌入 {len(rows)} 行")


def load_products(client, bucket):
    df = read_csv_object(bucket, "raw/products.csv")
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


def clean_daily_df(df: pd.DataFrame, dt) -> pd.DataFrame:
    df = df.dropna(subset=["product_id", "price"])
    df = df[df["price"] > 0]
    if df.empty:
        return df

    df["log_price"] = np.log(df["price"].astype(float))
    grouped = df.groupby("product_id", as_index=False).agg(
        category_id=("category_id", "first"),
        name=("name", "first"),
        log_price=("log_price", "mean"),
    )
    return pd.DataFrame({
        "dt": dt,
        "product_id": grouped["product_id"].astype("int64"),
        "category_id": grouped["category_id"].astype("int64"),
        "name": grouped["name"].astype(str),
        "price": np.exp(grouped["log_price"]).round(4),
    })


def list_daily_keys(bucket: oss2.Bucket) -> list[str]:
    keys = []
    for obj in oss2.ObjectIterator(bucket, prefix="raw/daily_price/"):
        if DATE_RE.match(obj.key):
            keys.append(obj.key)
    return sorted(keys)


def load_daily(client, bucket, limit=None):
    keys = list_daily_keys(bucket)
    if limit is not None:
        keys = keys[:limit]

    target = table("fact_sku_daily_price")
    client.command(f"TRUNCATE TABLE {target}")
    print(f"\n[fact_sku_daily_price] 开始从 OSS 灌入 {len(keys)} 个每日文件...")

    total_rows = 0
    for i, key in enumerate(keys, 1):
        m = DATE_RE.match(key)
        if not m:
            continue
        s = m.group(1)
        dt = pd.Timestamp(f"{s[0:4]}-{s[4:6]}-{s[6:8]}").date()
        out = clean_daily_df(read_csv_object(bucket, key), dt)
        if out.empty:
            continue
        client.insert_df(target, out)
        total_rows += len(out)
        if i % 20 == 0 or i == len(keys):
            print(f"  进度 {i}/{len(keys)}  累计灌入 {total_rows} 行")

    print(f"[fact_sku_daily_price] 完成，共灌入 {total_rows} 行")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5, help="只灌前 N 个每日文件；默认 5 个，用于 Actions smoke")
    parser.add_argument("--full", action="store_true", help="灌入 OSS raw/ 下全部每日文件")
    parser.add_argument("--skip-daily", action="store_true", help="只灌维表")
    args = parser.parse_args()

    limit = None if args.full else args.limit
    client = get_client()
    bucket = get_bucket()
    print(f"连接成功，Bucket={bucket.bucket_name}，开始从 OSS 灌入 ClickHouse...\n")

    load_categories(client, bucket)
    load_products(client, bucket)
    if not args.skip_daily:
        load_daily(client, bucket, limit=limit)

    print("\n=== 各表当前行数 ===")
    for t in ["dim_category", "dim_product", "fact_sku_daily_price"]:
        n = client.query(f"SELECT count() FROM {table(t)}").result_rows[0][0]
        print(f"  {t:24} {n}")


if __name__ == "__main__":
    main()
