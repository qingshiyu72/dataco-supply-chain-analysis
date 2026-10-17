# -*- coding: utf-8 -*-
"""
STEP 6 补充: XYZ 分类的双口径敏感性检验
问题: 按"周"聚合时, 118 个商品中 91 个被划为 Z 类(不稳定)。
      原因是订单数据在周粒度上过于稀疏 —— 一个商品一年 52 周里可能
      只有 10 周有订单, 其余 42 周被补 0, 把标准差抬得极高, CV 虚高。
做法: 同时按"月"聚合再算一次 CV, 两个口径对比。
      月度粒度降低了稀疏性影响, 更接近计划部门实际的计划周期。
定位: 主口径(月度)由 01_pipeline 产出; 本脚本只做独立复算与敏感性对比,
      不回写主表和策略矩阵, 避免两个脚本互相覆盖。
"""
import os
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "DataCoSupplyChainDataset.csv")
OUT = os.path.join(BASE, "outputs")

df = pd.read_csv(RAW, encoding="latin-1")
df["order_date"] = pd.to_datetime(df["order date (DateOrders)"], format="%m/%d/%Y %H:%M")
# 与 01_pipeline 相同的乱码修复 + 去空格。原始表里有 4 个商品名带尾随空格
# ("DVDs " / "Toys " / "Smart watch " / "Sports Books "), 不清洗就会在 reindex
# 时匹配不上主表名字, 被算成均值 NaN -> CV=0 -> 误判为 X 类。
df["Product Name"] = (df["Product Name"].astype(str)
                      .str.encode("latin-1", errors="ignore")
                      .str.decode("utf-8", errors="ignore")
                      .str.strip())

prod_master = pd.read_csv(os.path.join(OUT, "01_商品主表_含ABCXYZ.csv"))
products = prod_master["Product Name"].tolist()

def cv_by_freq(freq, label, period_freq=None, fill_zero=True):
    """按指定频率聚合需求并计算 CV

    freq        周期频率, 同时用于 to_period 和 period_range, 保证两侧对齐
    period_freq 兼容旧参数, 现与 freq 一致
    说明: 必须在 Period 层面做 reindex。若一侧用 to_period("W-MON")、
          另一侧用 date_range(freq="W-MON"), pandas 对周起点的定义不同
          (W-MON 表示"以周一结尾的那一周"), 会导致完全匹配不上、结果全 0。
    """
    pfreq = period_freq or freq
    d = df.copy()
    d["period"] = d["order_date"].dt.to_period(pfreq)
    g = d.groupby(["Product Name", "period"])["Order Item Quantity"].sum()
    pr = pd.period_range(d["period"].min(), d["period"].max(), freq=pfreq)
    idx = pd.MultiIndex.from_product([products, pr], names=["Product Name", "period"])
    full = g.reindex(idx, fill_value=0).reset_index()
    st = full.groupby("Product Name")["Order Item Quantity"].agg(
        均值="mean", 标准差="std", 期数="count"
    ).reset_index()
    st["CV"] = (st["标准差"] / st["均值"].replace(0, np.nan)).round(4).fillna(0)
    st = st.rename(columns={"均值": f"{label}_均值", "标准差": f"{label}_标准差", "CV": f"CV_{label}"})
    return st[["Product Name", f"CV_{label}"]]

def label(cv):
    if cv <= 0.5:
        return "X"
    if cv <= 1.0:
        return "Y"
    return "Z"

# 注意: W-SUN = 以周日结尾的周(即周一起), 与 01_pipeline 的 to_period("W") 一致;
# 若写成 W-MON, pandas 理解为"以周一结尾", 切割出的是周二~周一, 与主表对不上。
wk = cv_by_freq("W-SUN", "周")
mo = cv_by_freq("M", "月")

comp = prod_master[["Product Name", "ABC", "销售额", "销量", "CV_周", "CV_月"]].rename(
    columns={"CV_周": "CV_周_主表", "CV_月": "CV_月_主表"})
comp = comp.merge(wk, on="Product Name", how="left").merge(mo, on="Product Name", how="left")
comp["XYZ_周"] = comp["CV_周"].apply(label)
comp["XYZ_月"] = comp["CV_月"].apply(label)
# 独立复算 vs 主表: 两套实现分别算出 CV, 结果必须完全一致, 否则说明其中有 bug
comp["复算一致"] = (((comp["CV_周"] - comp["CV_周_主表"]).abs() < 1e-9)
                   & ((comp["CV_月"] - comp["CV_月_主表"]).abs() < 1e-9))

print("=" * 70)
print("XYZ 口径对比: 周 vs 月")
print("=" * 70)
print("\n【周口径分布】")
print(comp["XYZ_周"].value_counts().to_string())
print("\n【月口径分布】")
print(comp["XYZ_月"].value_counts().to_string())

print("\n【CV 统计对比】")
print(pd.DataFrame({
    "周口径": comp["CV_周"].describe(),
    "月口径": comp["CV_月"].describe(),
}).round(3).to_string())

print("\n【分类变动情况】")
print(pd.crosstab(comp["XYZ_周"], comp["XYZ_月"], margins=True).to_string())

print("\n【月口径下 X 类商品】")
print(comp[comp["XYZ_月"] == "X"].sort_values("CV_月")[
    ["Product Name", "ABC", "销售额", "CV_周", "CV_月"]].to_string(index=False))

# 本脚本只做敏感性对比, 不回写主表与策略矩阵 —— 主口径统一由 01_pipeline 产出。
# 否则先跑 02 再跑 01, 月口径会被覆盖回周口径, 两份输出互相打架。
comp["口径判定"] = np.where(comp["XYZ_周"] == comp["XYZ_月"], "不变", "变动")
comp.to_csv(os.path.join(OUT, "08_XYZ双口径对比.csv"), index=False, encoding="utf-8-sig")

print("\n" + "=" * 70)
print("与主表(01_pipeline 的结果)逐商品比对")
print("=" * 70)
print(f"CV 复算一致: {int(comp['复算一致'].sum())} / {len(comp)}")
if not comp["复算一致"].all():
    print("以下商品两套实现结果不一致, 需排查:")
    print(comp.loc[~comp["复算一致"],
                   ["Product Name", "CV_周_主表", "CV_周", "CV_月_主表", "CV_月"]].to_string(index=False))
print(f"\n周/月口径间换了档的商品: {(comp['口径判定'] == '变动').sum()} 个")
print("已导出:", os.path.join(OUT, "08_XYZ双口径对比.csv"))
