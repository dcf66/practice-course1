"""读取 price_index_daily，画出价格指数折线图（项目核心展示物）。

输出到 output/：
  - total_index_trend.png      总指数走势
  - category_index_trend.png   8 个一级类目指数走势
  - price_index_daily.csv      结果表导出（可上传 OSS result/）

用法： py scripts/plot_index.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 不弹窗，直接存文件
import matplotlib.pyplot as plt

from ch_client import get_client, table

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 中文字体（Windows 自带）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
matplotlib.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)
RESULT = table("price_index_daily")


def main():
    client = get_client()

    # 1) 总指数走势图
    df_total = client.query_df(
        f"SELECT dt, index_value FROM {RESULT} "
        f"WHERE index_level='总指数' ORDER BY dt"
    )
    plt.figure(figsize=(12, 5))
    plt.plot(df_total["dt"], df_total["index_value"], color="#c0392b", linewidth=1.5)
    plt.axhline(100, color="gray", linestyle="--", linewidth=0.8, label="基期=100")
    plt.title("高频电商价格指数 · 总指数走势（拉氏指数，基期 2025-05-17=100）")
    plt.xlabel("日期")
    plt.ylabel("指数值")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    p1 = OUT_DIR / "total_index_trend.png"
    plt.savefig(p1, dpi=130)
    plt.close()
    print(f"已生成 {p1}")

    # 2) 各一级类目指数走势图
    df_cat = client.query_df(
        f"SELECT dt, category_name, index_value FROM {RESULT} "
        f"WHERE index_level='类目指数' ORDER BY dt"
    )
    plt.figure(figsize=(12, 6))
    for name, g in df_cat.groupby("category_name"):
        plt.plot(g["dt"], g["index_value"], linewidth=1.1, label=name)
    plt.axhline(100, color="gray", linestyle="--", linewidth=0.8)
    plt.title("高频电商价格指数 · 一级类目指数走势（拉氏指数）")
    plt.xlabel("日期")
    plt.ylabel("指数值")
    plt.legend(fontsize=8, ncol=2)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    p2 = OUT_DIR / "category_index_trend.png"
    plt.savefig(p2, dpi=130)
    plt.close()
    print(f"已生成 {p2}")

    # 3) 导出结果表 CSV
    df_all = client.query_df(
        f"SELECT dt, index_level, category_name, index_type, "
        f"round(index_value,4) AS index_value FROM {RESULT} "
        f"ORDER BY dt, index_level, category_name"
    )
    p3 = OUT_DIR / "price_index_daily.csv"
    df_all.to_csv(p3, index=False, encoding="utf-8-sig")
    print(f"已导出 {p3}（{len(df_all)} 行）")


if __name__ == "__main__":
    main()
