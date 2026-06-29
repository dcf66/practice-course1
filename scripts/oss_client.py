"""OSS 连接配置：从 .env 读取密钥，返回一个可用的 bucket 对象。

其他脚本只要 `from oss_client import get_bucket` 就能拿到 OSS 连接，
不用在代码里出现任何密钥。
"""
import os
import sys
from pathlib import Path

import oss2
from dotenv import load_dotenv

# Windows 控制台可能不是 UTF-8，强制让 print 中文不报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 加载项目根目录下的 .env（本文件在 scripts/，根目录是上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")


def get_bucket() -> oss2.Bucket:
    """根据 .env 配置返回一个 OSS Bucket 对象。"""
    access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
    access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    endpoint = os.getenv("OSS_ENDPOINT")
    bucket_name = os.getenv("OSS_BUCKET")

    missing = [
        name
        for name, val in {
            "OSS_ACCESS_KEY_ID": access_key_id,
            "OSS_ACCESS_KEY_SECRET": access_key_secret,
            "OSS_ENDPOINT": endpoint,
            "OSS_BUCKET": bucket_name,
        }.items()
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"缺少环境变量: {', '.join(missing)}。请检查项目根目录的 .env 文件。"
        )

    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)


if __name__ == "__main__":
    # 直接运行本文件可测试连接是否正常
    bucket = get_bucket()
    print(f"连接成功，Bucket = {bucket.bucket_name}，Endpoint = {bucket.endpoint}")
    print("当前 bucket 里前 10 个对象：")
    count = 0
    for obj in oss2.ObjectIterator(bucket):
        print("  ", obj.key)
        count += 1
        if count >= 10:
            break
    if count == 0:
        print("  （空的，还没上传任何文件）")
