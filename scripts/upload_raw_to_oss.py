"""把本地 data/ 里的原始 CSV 上传到 OSS 的 raw/ 区。

OSS 目标结构：
  raw/products.csv
  raw/categories.csv
  raw/daily_price/dt=YYYYMMDD/daily_prices_YYYYMMDD.csv

特性：
  - 已存在且大小一致的文件会跳过，可随时中断后重跑（断点续传友好）。
  - 用法：
        python scripts/upload_raw_to_oss.py            # 上传全部
        python scripts/upload_raw_to_oss.py --limit 5  # 只传前 5 个每日文件（先小范围测试）
"""
import argparse
import re
import sys
from pathlib import Path

import oss2

from oss_client import get_bucket

# Windows 控制台可能不是 UTF-8，强制让 print 中文不报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# 从文件名 daily_prices_20250517.csv 里抠出日期 20250517
DATE_RE = re.compile(r"daily_prices_(\d{8})\.csv$")


def upload_one(bucket: oss2.Bucket, local_path: Path, oss_key: str) -> str:
    """上传单个文件，若 OSS 上已有同样大小的对象则跳过。返回状态字符串。"""
    local_size = local_path.stat().st_size
    if bucket.object_exists(oss_key):
        meta = bucket.head_object(oss_key)
        if meta.content_length == local_size:
            return "skip"
    bucket.put_object_from_file(oss_key, str(local_path))
    return "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="只上传前 N 个每日价格文件（用于先小范围测试）",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=DATA_DIR,
        help="本地原始数据目录，默认使用项目内 data/；可指定上级完整数据目录",
    )
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    daily_dir = data_dir / "daily_price"

    bucket = get_bucket()
    print(f"目标 Bucket: {bucket.bucket_name}\n")
    print(f"本地数据目录: {data_dir}\n")

    # 1) 两个维表
    for name in ["products.csv", "categories.csv"]:
        local = data_dir / name
        if not local.exists():
            print(f"[警告] 找不到 {local}，跳过")
            continue
        status = upload_one(bucket, local, f"raw/{name}")
        print(f"[{status:4}] raw/{name}")

    # 2) 每日价格文件
    daily_files = sorted(daily_dir.glob("daily_prices_*.csv"))
    if args.limit is not None:
        daily_files = daily_files[: args.limit]

    total = len(daily_files)
    print(f"\n开始上传 {total} 个每日价格文件...\n")
    uploaded = skipped = 0
    for i, local in enumerate(daily_files, 1):
        m = DATE_RE.search(local.name)
        if not m:
            print(f"[警告] 文件名不符合规则，跳过：{local.name}")
            continue
        dt = m.group(1)  # 20250517
        oss_key = f"raw/daily_price/dt={dt}/{local.name}"
        status = upload_one(bucket, local, oss_key)
        if status == "ok":
            uploaded += 1
        else:
            skipped += 1
        # 每 20 个或最后一个打印一次进度
        if i % 20 == 0 or i == total:
            print(f"  进度 {i}/{total}  新上传={uploaded}  跳过={skipped}")

    print(f"\n完成！新上传 {uploaded} 个，跳过 {skipped} 个（已存在）。")


if __name__ == "__main__":
    main()
