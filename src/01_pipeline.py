# -*- coding: utf-8 -*-
"""
供应链库存健康度诊断与安全库存优化 —— 主分析管线
数据源: DataCo Smart Supply Chain (180,519 行订单明细)
输出: outputs/*.csv  (供后续图表与文档引用)

运行: python 01_pipeline.py
"""
import os
import sys
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "DataCoSupplyChainDataset.csv")
OUT = os.path.join(BASE, "outputs")
os.makedirs(OUT, exist_ok=True)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)

def sec(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)

# ======================================================================
sec("STEP 1  数据装载与画像")
# 为什么: 先看清数据规模、类型、缺失情况, 再决定清洗策略
# 结果: 180,519 x 53; 24 文本 / 15 浮点 / 14 整数; 无日期类型
# ======================================================================
df = pd.read_csv(RAW, encoding="latin-1")
print(f"原始形状: {df.shape}")

prof = pd.DataFrame({
    "dtype": df.dtypes.astype(str),
    "缺失数": df.isna().sum(),
})
prof["缺失率%"] = (prof["缺失数"] / len(df) * 100).round(2)
prof["唯一值"] = df.nunique()
prof.to_csv(os.path.join(OUT, "00_字段画像.csv"), encoding="utf-8-sig")
print("\n全空列:", list(prof[prof["缺失率%"] == 100].index))
print("高缺失列(>50%):", list(prof[(prof["缺失率%"] > 50) & (prof["缺失率%"] < 100)].index))

# ======================================================================
sec("STEP 2  数据清洗")
# 为什么: 图像URL/脱敏密码/邮箱对分析无贡献, 保留会拖慢计算并干扰建模
# 结果: 53 -> 49 列
# ======================================================================
DROP = ["Product Image", "Customer Password", "Customer Email", "Order Zipcode"]
df = df.drop(columns=[c for c in DROP if c in df.columns])
print(f"清洗后形状: {df.shape}")

# 时间字段转 datetime
# 为什么: 字符串无法做时间序列聚合与提前期计算
df["order_date"] = pd.to_datetime(df["order date (DateOrders)"], format="%m/%d/%Y %H:%M")
df["ship_date"] = pd.to_datetime(df["shipping date (DateOrders)"], format="%m/%d/%Y %H:%M")
print(f"下单时间范围: {df['order_date'].min()} ~ {df['order_date'].max()}")

# 文本列 latin-1 乱码修复(如 Rajast��n)
# 为什么: 分组统计时乱码会把同一个州拆成多个组, 污染结果
for c in ["Order State", "Order City", "Customer State", "Customer City",
          "Product Name", "Category Name", "Department Name", "Order Country"]:
    if c in df.columns:
        df[c] = (df[c].astype(str)
                 .str.encode("latin-1", errors="ignore")
                 .str.decode("utf-8", errors="ignore")
                 .str.strip())
print("乱码修复完成, 示例:", df["Order State"].unique()[:5])

# ======================================================================
sec("STEP 3  特征工程: 延期天数")
# 为什么: 实际发货 vs 计划发货 的差值, 是衡量履约能力的核心指标,
#         也是安全库存中提前期(L)波动的事实依据
# 结果: 新增 delay_days, is_late
# ======================================================================
df["delay_days"] = df["Days for shipping (real)"] - df["Days for shipment (scheduled)"]
df["is_late"] = (df["delay_days"] > 0).astype(int)
df["lead_time"] = df["Days for shipping (real)"]

print(df["delay_days"].describe().round(3).to_string())
print(f"\n延期订单占比: {df['is_late'].mean()*100:.2f}%")
print(f"平均延期天数(仅延期单): {df.loc[df['is_late']==1,'delay_days'].mean():.2f} 天")
print("\nDelivery Status 分布:")
print(df["Delivery Status"].value_counts(normalize=True).mul(100).round(2).to_string())

# ======================================================================
sec("STEP 4  商品需求聚合 (ABC 基础)")
# 为什么: ABC 分类的对象必须是"商品", 需先把订单明细聚合成商品级需求
# 结果: 每个商品一行: 销售额/销量/订单数/均价
# ======================================================================
prod = df.groupby("Product Name").agg(
    销售额=("Sales", "sum"),
    销量=("Order Item Quantity", "sum"),
    订单数=("Order Id", "nunique"),
    订单行数=("Order Item Id", "count"),
    均价=("Product Price", "mean"),
    利润=("Order Profit Per Order", "sum"),
    实际提前期均值=("lead_time", "mean"),
    计划提前期均值=("Days for shipment (scheduled)", "mean"),
    延期率=("is_late", "mean"),
    品类=("Category Name", "first"),
    部门=("Department Name", "first"),
).reset_index()

prod["销售额"] = prod["销售额"].round(2)
prod["利润"] = prod["利润"].round(2)
prod["延期率"] = (prod["延期率"] * 100).round(2)
prod["实际提前期均值"] = prod["实际提前期均值"].round(2)
prod["计划提前期均值"] = prod["计划提前期均值"].round(2)
print(f"商品总数: {len(prod)}")
print(prod.sort_values("销售额", ascending=False).head(10).to_string(index=False))

# ======================================================================
sec("STEP 5  ABC 分类 (帕累托 / 二八法则)")
# 为什么: 资源有限, 必须把管理精力压在贡献 80% 销售额的少数商品上
#         这是库存管理最基本的分类法, 也是通用的资源分配切分方式
# 结果: A/B/C 三档, 边界为累计销售额 80% / 95%
# ======================================================================
prod = prod.sort_values("销售额", ascending=False).reset_index(drop=True)
prod["销售额累计"] = prod["销售额"].cumsum()
prod["累计占比"] = prod["销售额累计"] / prod["销售额"].sum()

def abc_label(p):
    if p <= 0.80:
        return "A"
    if p <= 0.95:
        return "B"
    return "C"

prod["ABC"] = prod["累计占比"].apply(abc_label)
prod["SKU排名"] = prod.index + 1

abc_stat = prod.groupby("ABC").agg(
    SKU数=("Product Name", "count"),
    销售额=("销售额", "sum"),
    销量=("销量", "sum"),
    平均延期率=("延期率", "mean"),
).reset_index()
abc_stat["SKU占比%"] = (abc_stat["SKU数"] / abc_stat["SKU数"].sum() * 100).round(2)
abc_stat["销售额占比%"] = (abc_stat["销售额"] / abc_stat["销售额"].sum() * 100).round(2)
abc_stat["销售额"] = abc_stat["销售额"].round(2)
print(abc_stat.to_string(index=False))

# ======================================================================
sec("STEP 6  XYZ 分类 (需求波动性)")
# 为什么: ABC 只看"金额重要性", 不看"需求稳定性";
#         波动大的商品即使金额小, 也可能因为断货造成严重缺货
#         用变异系数 CV = 标准差 / 均值 衡量
# 结果: X(CV<=0.5 稳定) / Y(0.5<CV<=1 波动) / Z(CV>1 很不稳定)
# ======================================================================
# 按 商品 x 周 聚合需求量, 构成周需求序列
df["week"] = df["order_date"].dt.to_period("W").dt.start_time
wk = df.groupby(["Product Name", "week"])["Order Item Quantity"].sum().reset_index()

# 完整周期对齐: 缺失周补 0(该周无订单=需求为0, 不能忽略)
all_weeks = pd.date_range(wk["week"].min(), wk["week"].max(), freq="W-MON")
full_idx = pd.MultiIndex.from_product([prod["Product Name"], all_weeks],
                                      names=["Product Name", "week"])
wk_full = (wk.set_index(["Product Name", "week"])
             .reindex(full_idx, fill_value=0)
             .reset_index())

xyz = wk_full.groupby("Product Name")["Order Item Quantity"].agg(
    周需求均值="mean", 周需求标准差="std", 周数="count"
).reset_index()
xyz["CV"] = (xyz["周需求标准差"] / xyz["周需求均值"].replace(0, np.nan)).round(4)
xyz["CV"] = xyz["CV"].fillna(0)

def xyz_label(cv):
    if cv <= 0.5:
        return "X"
    if cv <= 1.0:
        return "Y"
    return "Z"

xyz["XYZ"] = xyz["CV"].apply(xyz_label)

# 月口径: 订单在周粒度上过于稀疏(多数商品一年只有少数周有订单, 其余周补 0
#         会把标准差抬高、CV 虚高), 月度粒度更接近计划部门实际的计划周期。
#         因此以月度为主口径, 周度只作敏感性参考。
df["month"] = df["order_date"].dt.to_period("M")
mo = df.groupby(["Product Name", "month"])["Order Item Quantity"].sum()
all_months = pd.period_range(df["month"].min(), df["month"].max(), freq="M")
mo_idx = pd.MultiIndex.from_product([prod["Product Name"], all_months],
                                    names=["Product Name", "month"])
mo_full = mo.reindex(mo_idx, fill_value=0).reset_index()
xyz_mo = mo_full.groupby("Product Name")["Order Item Quantity"].agg(
    月需求均值="mean", 月需求标准差="std"
).reset_index()
xyz_mo["CV_月"] = (xyz_mo["月需求标准差"] / xyz_mo["月需求均值"].replace(0, np.nan)).round(4)
xyz_mo["CV_月"] = xyz_mo["CV_月"].fillna(0)
xyz_mo["XYZ_月"] = xyz_mo["CV_月"].apply(xyz_label)

xyz = xyz.rename(columns={"CV": "CV_周", "XYZ": "XYZ_周"})
prod = prod.merge(xyz[["Product Name", "周需求均值", "周需求标准差", "CV_周", "XYZ_周"]],
                  on="Product Name", how="left")
prod = prod.merge(xyz_mo[["Product Name", "CV_月", "XYZ_月"]], on="Product Name", how="left")
prod[["周需求均值", "周需求标准差"]] = prod[["周需求均值", "周需求标准差"]].round(2)

# CV / XYZ 取月口径(主口径); CV_周 / XYZ_周 保留作敏感性参考
prod["CV"] = prod["CV_月"]
prod["XYZ"] = prod["XYZ_月"]

print("【周口径】"); print(prod["XYZ_周"].value_counts().to_string())
print("\n【月口径(主口径)】"); print(prod["XYZ"].value_counts().to_string())
print("\nCV 分布(月口径):")
print(prod["CV"].describe().round(3).to_string())

# ======================================================================
sec("STEP 7  ABC-XYZ 九宫格矩阵")
# 为什么: 两个维度交叉后, 才形成"价值 x 波动"的可执行策略矩阵
#         这是本项目从"会算"到"会决策"的关键一步
# 结果: 9 个格子, 每格对应的管理策略
# ======================================================================
matrix = prod.groupby(["ABC", "XYZ"]).agg(
    SKU数=("Product Name", "count"),
    销售额=("销售额", "sum"),
    平均CV=("CV", "mean"),
).reset_index()
matrix["销售额占比%"] = (matrix["销售额"] / matrix["销售额"].sum() * 100).round(2)
matrix["平均CV"] = matrix["平均CV"].round(3)
matrix["销售额"] = matrix["销售额"].round(2)
print(matrix.to_string(index=False))

STRATEGY = {
    ("A", "X"): "核心稳定品|JIT准时制,低安全库存,高频小批补货,盯周转",
    ("A", "Y"): "核心波动品|重点管理,中等安全库存,滚动预测+周复盘",
    ("A", "Z"): "核心高危品|最高优先级,高安全库存,需与供应商签保供协议",
    ("B", "X"): "常规稳定品|系统自动补货,经济订货批量EOQ",
    ("B", "Y"): "常规波动品|定期review,适度安全库存",
    ("B", "Z"): "常规高危品|提高安全库存或考虑替换供应商/合并SKU",
    ("C", "X"): "长尾稳定品|简化管理,大批量低频次采购",
    ("C", "Y"): "长尾波动品|按订单采购,尽量降低持有",
    ("C", "Z"): "长尾高危品|考虑淘汰/替代,避免占用资金与仓储",
}
matrix["策略"] = matrix.apply(lambda r: STRATEGY.get((r["ABC"], r["XYZ"]), ""), axis=1)
# 导出放在 STEP 8 之后: 策略矩阵里要带上"平均安全库存", 依赖 STEP 8 的结果

# ======================================================================
sec("STEP 8  安全库存与再订货点")
# 为什么: 这是把分析落成"可执行决策"的一步 —— 每个商品该备多少货
# 公式: SS = Z x sigma_d x sqrt(L)
#       Z 按 ABC 分档 (A 99% / B 95% / C 90%), sigma_d=周需求标准差, L=提前期(周)
#       ROP = 周均需求 x L + SS
# 为什么分档: 服务水平每提高一档, 安全库存按 Z 值比例上升, 资金占用随之上升。
#         统一用 95% 等于给"贡献 5% 销售额的长尾品"和"贡献 77% 的头部品"同样待遇,
#         把管理资源平摊掉了 —— 这与 ABC 分类的初衷矛盾。
# 结果: 每个商品按自身重要性定服务水平的安全库存与再订货点建议值
# ======================================================================
Z_BY_ABC = {"A": 2.326, "B": 1.645, "C": 1.282}   # 99% / 95% / 90%
SERVICE_BY_ABC = {"A": 99, "B": 95, "C": 90}
prod["服务水平%"] = prod["ABC"].map(SERVICE_BY_ABC)
prod["Z值"] = prod["ABC"].map(Z_BY_ABC)
prod["提前期_周"] = (prod["实际提前期均值"] / 7).round(4)
prod["安全库存"] = (prod["Z值"] * prod["周需求标准差"] * np.sqrt(prod["提前期_周"])).round(2)
prod["再订货点"] = (prod["周需求均值"] * prod["提前期_周"] + prod["安全库存"]).round(2)
prod["安全库存/周需求"] = (prod["安全库存"] / prod["周需求均值"].replace(0, np.nan)).round(2)

# 分档 vs 统一 95% 的对比: 用来说明分档到底改变了什么
ss_flat = (1.645 * prod["周需求标准差"] * np.sqrt(prod["提前期_周"])).sum()
ss_tier = prod["安全库存"].sum()
print(f"安全库存合计: 统一 Z=1.645(95%) -> {ss_flat:,.0f} 件; "
      f"按 ABC 分档 -> {ss_tier:,.0f} 件 ({(ss_tier / ss_flat - 1) * 100:+.1f}%)")
print("按 ABC 看安全库存去向:")
print(prod.groupby("ABC")["安全库存"].agg(SKU数="count", 合计="sum", 平均="mean")
      .round(2).to_string())

# 策略矩阵补上"平均安全库存"后导出
ss_avg = prod.groupby(["ABC", "XYZ"])["安全库存"].mean().round(2)
ss_avg = ss_avg.rename("平均安全库存").reset_index()
matrix = matrix.merge(ss_avg, on=["ABC", "XYZ"], how="left")
matrix.to_csv(os.path.join(OUT, "04_ABC_XYZ矩阵.csv"), index=False, encoding="utf-8-sig")

print("安全库存统计:")
print(prod["安全库存"].describe().round(2).to_string())
print("\n安全库存 TOP10:")
print(prod.nlargest(10, "安全库存")[
    ["Product Name", "ABC", "XYZ", "周需求均值", "周需求标准差", "提前期_周", "安全库存", "再订货点"]
].to_string(index=False))

# ======================================================================
sec("STEP 9  履约与提前期诊断")
# 为什么: 安全库存的 sqrt(L) 项说明——提前期越长越不稳定, 安全库存越高
#         所以必须回头看: 我们的提前期到底稳不稳, 谁在拖后腿
# 结果: 按配送方式/市场/区域 拆解延期情况
# ======================================================================
print("【按配送方式】")
sm = df.groupby("Shipping Mode").agg(
    订单数=("Order Id", "count"),
    平均实际提前期=("lead_time", "mean"),
    平均计划提前期=("Days for shipment (scheduled)", "mean"),
    平均延期=("delay_days", "mean"),
    延期率=("is_late", "mean"),
).round(3)
sm["延期率"] = (sm["延期率"] * 100).round(2)
print(sm.to_string())
sm.to_csv(os.path.join(OUT, "05_配送方式履约.csv"), encoding="utf-8-sig")

print("\n【按市场】")
mk = df.groupby("Market").agg(
    订单数=("Order Id", "count"),
    销售额=("Sales", "sum"),
    平均延期=("delay_days", "mean"),
    延期率=("is_late", "mean"),
).round(3)
mk["延期率"] = (mk["延期率"] * 100).round(2)
mk["销售额占比%"] = (mk["销售额"] / mk["销售额"].sum() * 100).round(2)
print(mk.sort_values("销售额", ascending=False).to_string())
mk.to_csv(os.path.join(OUT, "06_市场履约.csv"), encoding="utf-8-sig")

print("\n【延期最严重的 10 个区域】")
rg = df.groupby("Order Region").agg(
    订单数=("Order Id", "count"),
    平均延期=("delay_days", "mean"),
    延期率=("is_late", "mean"),
).round(3)
rg["延期率"] = (rg["延期率"] * 100).round(2)
print(rg.sort_values("延期率", ascending=False).head(10).to_string())
rg.to_csv(os.path.join(OUT, "07_区域履约.csv"), encoding="utf-8-sig")

print("\n【订单状态分布】")
osd = df["Order Status"].value_counts(normalize=True).mul(100).round(2)
print(osd.to_string())

# ======================================================================
sec("STEP 10  导出结果")
# ======================================================================
prod_sorted = prod.sort_values("销售额", ascending=False)
prod_sorted.to_csv(os.path.join(OUT, "01_商品主表_含ABCXYZ.csv"), index=False, encoding="utf-8-sig")
abc_stat.to_csv(os.path.join(OUT, "02_ABC统计.csv"), index=False, encoding="utf-8-sig")
xyz_stat = prod.groupby("XYZ").agg(
    SKU数=("Product Name", "count"),
    销售额=("销售额", "sum"),
    平均CV=("CV", "mean"),
).reset_index()
xyz_stat["销售额"] = xyz_stat["销售额"].round(2)
xyz_stat["平均CV"] = xyz_stat["平均CV"].round(3)
xyz_stat.to_csv(os.path.join(OUT, "03_XYZ统计.csv"), index=False, encoding="utf-8-sig")

print("已导出:")
for f in sorted(os.listdir(OUT)):
    print("  ", f)

# ======================================================================
sec("核心结论速览（可直接引用）")
# ======================================================================
n_late = int(df["is_late"].sum())
print(f"1. 数据规模: {len(df):,} 条订单明细, {prod['Product Name'].nunique()} 个商品")
print(f"2. 延期订单 {n_late:,} 单, 占比 {df['is_late'].mean()*100:.2f}%, "
      f"平均延期 {df.loc[df['is_late']==1,'delay_days'].mean():.2f} 天")
print(f"3. A 类商品 {int((prod['ABC']=='A').sum())} 个, "
      f"贡献 {abc_stat.loc[abc_stat['ABC']=='A','销售额占比%'].values[0]:.2f}% 销售额")
print(f"4. 需求不稳定(Z类)商品 {int((prod['XYZ']=='Z').sum())} 个, "
      f"平均 CV={prod.loc[prod['XYZ']=='Z','CV'].mean():.2f}")
print(f"5. 安全库存合计建议 {prod['安全库存'].sum():,.0f} 件")
