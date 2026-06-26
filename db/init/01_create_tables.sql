-- 高频电商价格指数：ClickHouse 表结构
-- 容器首次启动时自动执行。字段对齐 design_guide.md 与 data/ 里的真实 CSV 列。

CREATE DATABASE IF NOT EXISTS price_index;

-- 明细事实表：每天每个 SKU 一条价格记录
-- 数据来源: data/daily_price/daily_prices_YYYYMMDD.csv
--   CSV 列: product_id, category_id, name, price, change_date
CREATE TABLE IF NOT EXISTS price_index.fact_sku_daily_price
(
    dt           Date,          -- 价格日期 (change_date)
    product_id   UInt64,        -- SKU 唯一标识
    category_id  UInt64,        -- 所属类目
    name         String,        -- 商品名
    price        Float64        -- 当日价格
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(dt)                       -- 按月分区，避免单查询扫全量
ORDER BY (dt, category_id, product_id);         -- 按天+类目排序，聚合飞快

-- 商品维表（含权重）：来源 data/products.csv
--   CSV 列: product_id, category_id, name, weight, price, change_count
CREATE TABLE IF NOT EXISTS price_index.dim_product
(
    product_id    UInt64,
    category_id   UInt64,
    name          String,
    weight        Float64,      -- 指数权重
    base_price    Float64,      -- 基期价格
    change_count  UInt32
)
ENGINE = MergeTree
ORDER BY (product_id);

-- 类目维表（含权重）：来源 data/categories.csv
--   CSV 列: category, category_id, hierarchy, weight, price, parent
CREATE TABLE IF NOT EXISTS price_index.dim_category
(
    category_name  String,      -- category
    category_id    UInt64,
    hierarchy      UInt8,        -- 层级
    weight         Float64,
    price          Nullable(Float64),
    parent         Nullable(UInt64)
)
ENGINE = MergeTree
ORDER BY (category_id);

-- 指数结果表：来源 = 计算模块的输出
CREATE TABLE IF NOT EXISTS price_index.price_index_daily
(
    dt             Date,        -- 计算日期
    index_level    String,      -- 层级: 总指数 / 类目指数
    category_name  String,      -- 具体类目名（总指数时填 '__ALL__'）
    index_type     String,      -- 算法: laspeyres(拉氏) / fisher(费雪)
    index_value    Float64      -- 指数值
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(dt)
ORDER BY (dt, index_level, category_name, index_type);
