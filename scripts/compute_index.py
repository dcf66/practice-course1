"""核心指数计算：从 fact_sku_daily_price 算出拉氏价格指数，写入 price_index_daily。

方法（拉氏指数 Laspeyres，固定基期篮子）：
  - 基期 = 最早一天，指数 = 100。基期篮子 = 基期当天有价的 SKU。
  - SKU 价格相对数 R = 当日价 / 基期价。
  - SKU 全局权重 W = 商品权重(叶子内归一) × 叶子类目权重(全体归一)，ΣW = 1。
  - 总指数   = Σ(W·R) / Σ(W) × 100        （在当天可比 SKU 上归一）
  - 类目指数 = 同上，但限定在某个一级类目下的 SKU
  说明：本数据没有逐日销量，权重用维表固定 weight（方案 A）。因此费雪指数会退化
        为拉氏指数，本项目以拉氏指数为准，不单独输出费雪。

所有聚合在 ClickHouse 服务端用 INSERT ... SELECT 完成（2600 万行）。
可反复运行：每次先清空结果表。

用法： py scripts/compute_index.py
"""
import sys
from pathlib import Path

from ch_client import get_client, table

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

FACT = table("fact_sku_daily_price")
RESULT = table("price_index_daily")
DIM_PRODUCT = table("dim_product")
DIM_CATEGORY = table("dim_category")

# 公共 CTE：基期价 base(p0) 和 SKU 全局权重 skuw(w)，并带一级类目 id(l1)
COMMON_WITH = f"""
WITH
  base AS (
      SELECT product_id, price AS p0
      FROM {FACT}
      WHERE dt = (SELECT min(dt) FROM {FACT})
  ),
  skuw AS (
      SELECT
          dp.product_id AS pid,
          intDiv(dp.category_id, 1000000) * 1000000 AS l1,
          dp.weight * dc.weight AS w
      FROM {DIM_PRODUCT} dp
      INNER JOIN {DIM_CATEGORY} dc ON dp.category_id = dc.category_id
  )
"""

# 总指数：每天一行
SQL_TOTAL = f"""
INSERT INTO {RESULT}
{COMMON_WITH}
SELECT
    f.dt                                      AS dt,
    '总指数'                                  AS index_level,
    '__ALL__'                                 AS category_name,
    'laspeyres'                               AS index_type,
    sum(s.w * f.price / b.p0) / sum(s.w) * 100 AS index_value
FROM {FACT} f
INNER JOIN base AS b ON f.product_id = b.product_id
INNER JOIN skuw AS s ON f.product_id = s.pid
GROUP BY f.dt
"""

# 类目指数：每天每个一级类目一行
SQL_CATEGORY = f"""
INSERT INTO {RESULT}
{COMMON_WITH}
SELECT
    f.dt                                       AS dt,
    '类目指数'                                 AS index_level,
    dc1.category_name                          AS category_name,
    'laspeyres'                                AS index_type,
    sum(s.w * f.price / b.p0) / sum(s.w) * 100 AS index_value
FROM {FACT} f
INNER JOIN base AS b   ON f.product_id = b.product_id
INNER JOIN skuw AS s   ON f.product_id = s.pid
INNER JOIN {DIM_CATEGORY} dc1 ON dc1.category_id = s.l1
WHERE dc1.hierarchy = 1
GROUP BY f.dt, dc1.category_name
"""


def main():
    client = get_client()
    print("连接成功，开始计算拉氏指数...")

    client.command(f"TRUNCATE TABLE {RESULT}")

    print("  计算总指数...")
    client.command(SQL_TOTAL)
    print("  计算各一级类目指数...")
    client.command(SQL_CATEGORY)

    # 汇总检查
    n = client.query(f"SELECT count() FROM {RESULT}").result_rows[0][0]
    print(f"\n完成，结果表共 {n} 行。")

    print("\n=== 总指数（首尾各 5 天）===")
    head = client.query(
        f"SELECT dt, round(index_value,2) FROM {RESULT} "
        f"WHERE index_level='总指数' ORDER BY dt LIMIT 5"
    ).result_rows
    tail = client.query(
        f"SELECT dt, round(index_value,2) FROM {RESULT} "
        f"WHERE index_level='总指数' ORDER BY dt DESC LIMIT 5"
    ).result_rows
    for r in head:
        print("  ", r)
    print("   ...")
    for r in reversed(tail):
        print("  ", r)

    print("\n=== 各类目最新一天指数 ===")
    rows = client.query(
        f"""SELECT category_name, round(index_value,2) FROM {RESULT}
            WHERE index_level='类目指数'
              AND dt=(SELECT max(dt) FROM {RESULT})
            ORDER BY index_value DESC"""
    ).result_rows
    for r in rows:
        print("  ", r)


if __name__ == "__main__":
    main()
