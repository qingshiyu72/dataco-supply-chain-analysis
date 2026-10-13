# -*- coding: utf-8 -*-
"""
STEP 6 补充: XYZ 分类的双口径交叉验证
问题: 按"周"聚合时, 118 个商品中 91 个被划为 Z 类(不稳定)。
      原因是订单数据在周粒度上过于稀疏 —— 一个商品一年 52 周里可能
      只有 10 周有订单, 其余 42 周被补 0, 把标准差抬得极高, CV 虚高。
做法: 同时按"月"聚合再算一次 CV, 两个口径对比。
      月度粒度降低了稀疏性影响, 更接近计划部门实际的计划周期。
结论: 以月度口径为主 (更稳健), 周度口径作为敏感性参考。
"""
import os
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "DataCoSupplyChainDataset.csv")
OUT = os.path.join(BASE, "outputs")

df = pd.read_csv(RAW, encoding="latin-1")
df["order_date"] = pd.to_datetime(df["order date (DateOrders)"], format="%m/%d/%Y %H:%M")

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

wk = cv_by_freq("W-MON", "周")
mo = cv_by_freq("M", "月")

comp = prod_master[["Product Name", "ABC", "销售额", "销量", "CV"]].rename(columns={"CV": "CV_周_旧"})
comp = comp.merge(wk, on="Product Name").merge(mo, on="Product Name")
comp["XYZ_周"] = comp["CV_周"].apply(label)
comp["XYZ_月"] = comp["CV_月"].apply(label)

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

# 用月口径替换主表 XYZ, 重新导出
final = prod_master.drop(columns=["CV", "XYZ"]).merge(
    comp[["Product Name", "CV_月", "XYZ_月"]].rename(columns={"CV_月": "CV", "XYZ_月": "XYZ"}),
    on="Product Name"
)
# 重算安全库存(基于月需求 -> 周需求)
final = final.drop(columns=[c for c in ["安全库存", "再订货点", "安全库存/周需求"] if c in final.columns])
final["提前期_周"] = (final["实际提前期均值"] / 7).round(4)
final["安全库存"] = (1.65 * final["周需求标准差"] * np.sqrt(final["提前期_周"])).round(2)
final["再订货点"] = (final["周需求均值"] * final["提前期_周"] + final["安全库存"]).round(2)
final = final.sort_values("销售额", ascending=False)
final.to_csv(os.path.join(OUT, "01_商品主表_含ABCXYZ.csv"), index=False, encoding="utf-8-sig")
comp.to_csv(os.path.join(OUT, "08_XYZ双口径对比.csv"), index=False, encoding="utf-8-sig")

abc_xyz = final.groupby(["ABC", "XYZ"]).agg(
    SKU数=("Product Name", "count"),
    销售额=("销售额", "sum"),
    平均CV=("CV", "mean"),
    平均安全库存=("安全库存", "mean"),
).reset_index()
abc_xyz["销售额占比%"] = (abc_xyz["销售额"] / abc_xyz["销售额"].sum() * 100).round(2)
abc_xyz["平均CV"] = abc_xyz["平均CV"].round(3)
abc_xyz["平均安全库存"] = abc_xyz["平均安全库存"].round(2)
abc_xyz["销售额"] = abc_xyz["销售额"].round(2)

STRATEGY = {
    ("A", "X"): "核心稳定品|JIT准时制,低安全库存,高频小批补货,盯周转",
    ("A", "Y"): "核心波动品|重点管理,中等安全库存,滚动预测+周复盘",
    ("A", "Z"): "核心高危品|最高优先级,高安全库存,与供应商签保供协议",
    ("B", "X"): "常规稳定品|系统自动补货,经济订货批量EOQ",
    ("B", "Y"): "常规波动品|定期review,适度安全库存",
    ("B", "Z"): "常规高危品|提高安全库存或替换供应商/合并SKU",
    ("C", "X"): "长尾稳定品|简化管理,大批量低频次采购",
    ("C", "Y"): "长尾波动品|按订单采购,尽量降低持有",
    ("C", "Z"): "长尾高危品|考虑淘汰/替代,避免占用资金与仓储",
}
abc_xyz["策略"] = abc_xyz.apply(lambda r: STRATEGY.get((r["ABC"], r["XYZ"]), ""), axis=1)
abc_xyz.to_csv(os.path.join(OUT, "04_ABC_XYZ矩阵.csv"), index=False, encoding="utf-8-sig")

print("\n" + "=" * 70)
print("修正后 ABC-XYZ 矩阵 (月度口径)")
print("=" * 70)
print(abc_xyz.to_string(index=False))

print("\n最终核心结论:")
print(f"1. A类商品 {int((final['ABC']=='A').sum())} 个, "
      f"贡献 {final.loc[final['ABC']=='A','销售额'].sum()/final['销售额'].sum()*100:.2f}% 销售额")
for t in ["X", "Y", "Z"]:
    sub = final[final["XYZ"] == t]
    print(f"   {t}类 {len(sub)} 个, 销售额占比 {sub['销售额'].sum()/final['销售额'].sum()*100:.2f}%")
print(f"2. 安全库存合计 {final['安全库存'].sum():,.0f} 件")
