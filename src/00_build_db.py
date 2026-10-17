# -*- coding: utf-8 -*-
"""
STEP 0  SQLite 建库 + ABC 分类的 SQL 实现
为什么: 18 万行明细每次都从 CSV 全表重算, 慢且不能按条件取数;
       落成 SQLite 后可用窗口函数一次算完累计占比, 便于复查与二次取数。
输出: data/supplychain.db          表 order_items (180,519 行)
      outputs/09_SQL_ABC校验.csv   每个 SKU 的累计占比与 ABC 档位
校验: SQL 窗口函数的结果与 pandas cumsum 口径逐商品比对, 必须 118/118 一致。

运行: python 00_build_db.py
"""
import os
import sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "DataCoSupplyChainDataset.csv")
DB = os.path.join(BASE, "data", "supplychain.db")
OUT = os.path.join(BASE, "outputs")
os.makedirs(OUT, exist_ok=True)

if os.path.exists(DB):
    os.remove(DB)          # 每次重建, 保证与原始 CSV 一致, 不做增量

print(f"SQLite 版本: {sqlite3.sqlite_version}")
df = pd.read_csv(RAW, encoding="latin-1")
print(f"原始形状: {df.shape}")

# 与 01_pipeline 一致: 剔除对分析无贡献的列
DROP = ["Product Image", "Customer Password", "Customer Email", "Order Zipcode"]
df = df.drop(columns=[c for c in DROP if c in df.columns])
# 商品名做同样的乱码修复 + 去空格, 否则带尾随空格的 4 个 SKU 会被分成两组
df["Product Name"] = (df["Product Name"].astype(str)
                      .str.encode("latin-1", errors="ignore")
                      .str.decode("utf-8", errors="ignore")
                      .str.strip())

conn = sqlite3.connect(DB)
df.to_sql("order_items", conn, index=False, chunksize=20000)
conn.execute('CREATE INDEX idx_product ON order_items("Product Name")')
conn.commit()

n_rows = conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
n_sku = conn.execute('SELECT COUNT(DISTINCT "Product Name") FROM order_items').fetchone()[0]
print(f"入库: {n_rows:,} 行 / {n_sku} 个 SKU")

# ---------------------------------------------------------------- SQL 版 ABC
# 窗口函数一次算完累计销售额占比, 再按 80% / 95% 分档
SQL_ABC = """
WITH p AS (
    SELECT "Product Name" AS product,
           SUM(Sales) AS sales,
           SUM("Order Item Quantity") AS qty
    FROM order_items
    GROUP BY "Product Name"
), c AS (
    SELECT product, sales, qty,
           SUM(sales) OVER (ORDER BY sales DESC
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             * 1.0 / SUM(sales) OVER () AS cum_share,
           ROW_NUMBER() OVER (ORDER BY sales DESC) AS rnk
    FROM p
)
SELECT rnk, product, sales, qty, ROUND(cum_share, 6) AS cum_share,
       CASE WHEN cum_share <= 0.80 THEN 'A'
            WHEN cum_share <= 0.95 THEN 'B'
            ELSE 'C' END AS abc
FROM c
ORDER BY rnk
"""
sql_res = pd.read_sql(SQL_ABC, conn)
sql_res.to_csv(os.path.join(OUT, "09_SQL_ABC校验.csv"), index=False, encoding="utf-8-sig")

print("\nSQL 口径 ABC 分布:")
print(sql_res.groupby("abc").agg(SKU数=("product", "count"),
                                销售额=("sales", "sum")).to_string())

# ---------------------------------------------------------------- 交叉校验
# 同一张表, 用 pandas 再算一遍累计占比, 与 SQL 结果逐商品比对
chk = pd.read_sql('SELECT "Product Name" AS product, Sales AS sales FROM order_items', conn)
chk = chk.groupby("product", as_index=False)["sales"].sum().sort_values("sales", ascending=False)
chk["cum_share"] = chk["sales"].cumsum() / chk["sales"].sum()


def abc_label(p):
    if p <= 0.80:
        return "A"
    if p <= 0.95:
        return "B"
    return "C"


chk["abc_pandas"] = chk["cum_share"].apply(abc_label)
merged = sql_res.merge(chk[["product", "abc_pandas"]], on="product", how="left")
bad = merged[merged["abc"] != merged["abc_pandas"]]

print(f"\n交叉校验(SQL 窗口函数 vs pandas cumsum): "
      f"{len(merged) - len(bad)} / {len(merged)} 一致")
if len(bad):
    print("不一致商品:")
    print(bad[["rnk", "product", "cum_share", "abc", "abc_pandas"]].to_string(index=False))

conn.close()
print(f"\n已生成: {DB}")
print(f"已生成: {os.path.join(OUT, '09_SQL_ABC校验.csv')}")
