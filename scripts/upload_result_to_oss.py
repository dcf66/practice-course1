"""上传 output/ 下的结果文件到 OSS result/。"""
import sys
from pathlib import Path

from oss_client import get_bucket

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "output"
FILES = [
    "price_index_daily.csv",
    "total_index_trend.png",
    "category_index_trend.png",
]


def main():
    bucket = get_bucket()
    for name in FILES:
        path = OUT_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"缺少输出文件: {path}")
        key = f"result/{name}"
        bucket.put_object_from_file(key, str(path))
        meta = bucket.head_object(key)
        print(f"{key} bytes={meta.content_length} local_bytes={path.stat().st_size}")


if __name__ == "__main__":
    main()
