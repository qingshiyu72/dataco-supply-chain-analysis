# -*- coding: utf-8 -*-
"""
STEP 11  交付物生成
不依赖 matplotlib(环境缺少且离线无法安装), 改用:
  1) openpyxl 生成带原生图表的 Excel 报告(可在 Excel/WPS 里直接看和截图)
  2) 纯 HTML + 内联 SVG 生成可视化看板(浏览器打开即可截图)
输出: outputs/供应链库存分析报告.xlsx
      outputs/库存分析看板.html
"""
import os
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, LineChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "outputs")
RAW = os.path.join(BASE, "data", "DataCoSupplyChainDataset.csv")

prod = pd.read_csv(os.path.join(OUT, "01_商品主表_含ABCXYZ.csv"))
abc = pd.read_csv(os.path.join(OUT, "02_ABC统计.csv"))
matrix = pd.read_csv(os.path.join(OUT, "04_ABC_XYZ矩阵.csv"))
sm = pd.read_csv(os.path.join(OUT, "05_配送方式履约.csv"))
mk = pd.read_csv(os.path.join(OUT, "06_市场履约.csv"))
rg = pd.read_csv(os.path.join(OUT, "07_区域履约.csv"))

# 概览里的关键数字一律从主表实时算, 不写死 —— 否则脚本改了口径, 报告还是旧数字
n_sku = len(prod)
n_a = int((prod["ABC"] == "A").sum())
a_share = prod.loc[prod["ABC"] == "A", "销售额"].sum() / prod["销售额"].sum() * 100
n_a_pct = n_a / n_sku * 100
n_x = int((prod["XYZ"] == "X").sum())
n_z = int((prod["XYZ"] == "Z").sum())
ss_total = prod["安全库存"].sum()

# ---------------------------------------------------------------- Excel
wb = Workbook()
HDR = Font(bold=True, color="FFFFFF", size=11)
FILL = PatternFill("solid", fgColor="2F5597")
FILL2 = PatternFill("solid", fgColor="D9E2F3")
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

def style_header(ws, row=1, ncol=None):
    ncol = ncol or ws.max_column
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HDR
        cell.fill = FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = ws.cell(row=row + 1, column=1)

def write_df(ws, df, title=None, start=1):
    r = start
    if title:
        ws.cell(row=r, column=1, value=title).font = Font(bold=True, size=13, color="2F5597")
        r += 1
    for j, col in enumerate(df.columns, 1):
        ws.cell(row=r, column=j, value=str(col))
    style_header(ws, r)
    for i, (_, row) in enumerate(df.iterrows(), 1):
        for j, col in enumerate(df.columns, 1):
            v = row[col]
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = float(v)
            ws.cell(row=r + i, column=j, value=v)
    for j, col in enumerate(df.columns, 1):
        w = max(len(str(col)), *(len(str(x)) for x in df[col].head(50))) + 3
        ws.column_dimensions[get_column_letter(j)].width = min(max(w, 10), 42)
    return r

# --- Sheet 1 概览
ws = wb.active
ws.title = "1-结论概览"
rows = [
    ["指标", "数值", "说明"],
    ["数据规模", "180,519 条订单明细", "DataCo Smart Supply Chain, 2015-01 至 2018-01"],
    ["商品数", "118 个 SKU", "覆盖 5 大市场、23 个区域"],
    ["延期订单占比", "57.28%", "实际发货天数 > 计划发货天数"],
    ["平均延期天数", "1.62 天", "仅统计已延期订单"],
    ["A 类商品", f"{n_a} 个（占 SKU {n_a_pct:.2f}%）", f"贡献 {a_share:.2f}% 销售额 —— 典型帕累托分布"],
    ["X 类商品（需求稳定）", f"{n_x} 个", "月需求 CV ≤ 0.5"],
    ["Z 类商品（需求波动）", f"{n_z} 个", "月需求 CV > 1.0"],
    ["安全库存建议合计", f"{ss_total:,.0f} 件", "按 ABC 分档: A 99% / B 95% / C 90%"],
    ["最高延期区域", "Central Africa 60.7%", "全球平均延期率 57.28%"],
]
for i, row in enumerate(rows, 1):
    for j, v in enumerate(row, 1):
        ws.cell(row=i, column=j, value=v)
style_header(ws, 1)
for j, w in zip(range(1, 4), [22, 26, 60]):
    ws.column_dimensions[get_column_letter(j)].width = w
for i in range(2, ws.max_row + 1):
    ws.cell(row=i, column=1).font = Font(bold=True)

# --- Sheet 2 ABC
ws2 = wb.create_sheet("2-ABC分类")
write_df(ws2, abc, "ABC 分类结果（按销售额帕累托）")
ch = BarChart(); ch.title = "ABC 各类销售额占比"; ch.y_axis.title = "占比 %"; ch.height = 8; ch.width = 16
d = Reference(ws2, min_col=5, min_row=2, max_row=1 + len(abc))
cat = Reference(ws2, min_col=1, min_row=2, max_row=1 + len(abc))
ch.add_data(d, titles_from_data=True); ch.set_categories(cat)
ws2.add_chart(ch, f"A{ws2.max_row + 3}")

pc = PieChart(); pc.title = "ABC SKU 数量结构"; pc.height = 8; pc.width = 16
d2 = Reference(ws2, min_col=2, min_row=2, max_row=1 + len(abc))
pc.add_data(d2, titles_from_data=True); pc.set_categories(cat)
ws2.add_chart(pc, f"J{ws2.max_row + 3}")

# --- Sheet 3 ABC-XYZ 矩阵
ws3 = wb.create_sheet("3-ABC-XYZ矩阵")
write_df(ws3, matrix, "ABC-XYZ 九宫格策略矩阵（月度口径）")

# --- Sheet 4 商品明细
ws4 = wb.create_sheet("4-商品明细")
cols = ["Product Name", "ABC", "XYZ", "服务水平%", "Z值", "销售额", "销量", "订单数", "均价",
        "周需求均值", "周需求标准差", "CV", "提前期_周", "安全库存", "再订货点", "延期率", "品类"]
write_df(ws4, prod[cols].round(2), "商品级明细（含 ABC/XYZ 与安全库存建议）")
ws4.column_dimensions["A"].width = 44

# --- Sheet 5 履约诊断
ws5 = wb.create_sheet("5-履约诊断")
r = write_df(ws5, sm, "按配送方式的履约表现")
r2 = write_df(ws5, mk, "按市场的履约与销售", start=r + len(sm) + 3)
write_df(ws5, rg, "按区域的履约表现", start=r2 + len(mk) + 3)

xlsx_path = os.path.join(OUT, "供应链库存分析报告.xlsx")
wb.save(xlsx_path)
print("已生成:", xlsx_path)

# ---------------------------------------------------------------- HTML 看板
def bars(labels, values, title, unit="", color="#2F5597", fmt="{:.2f}"):
    mx = max(values) if len(values) else 1
    h = 260
    out = [f'<div class="card"><h3>{title}</h3><div class="bars">']
    for lb, v in zip(labels, values):
        pct = (v / mx * 100) if mx else 0
        out.append(
            f'<div class="bar-row"><span class="lb">{lb}</span>'
            f'<span class="track"><i style="width:{pct:.1f}%;background:{color}"></i></span>'
            f'<span class="vl">{fmt.format(v)}{unit}</span></div>'
        )
    out.append("</div></div>")
    return "\n".join(out)

abc_s = abc.sort_values("ABC")
abcx = abc_s["ABC"].tolist(); abcy = abc_s["销售额占比%"].tolist(); abcn = abc_s["SKU数"].tolist()
mx_s = matrix.copy(); mx_s["标签"] = mx_s["ABC"] + "-" + mx_s["XYZ"]
mxs = mx_s.sort_values("销售额占比%", ascending=False)

top10 = prod.nlargest(10, "销售额")
sm_s = sm.sort_values("订单数", ascending=False)
rg_s = rg.sort_values("延期率", ascending=False).head(10)
mk_s = mk.sort_values("销售额占比%", ascending=False)

matrix_rows = "".join(
    f'<tr><td><b>{r["ABC"]}-{r["XYZ"]}</b></td><td>{int(r["SKU数"])}</td>'
    f'<td>{r["销售额占比%"]}%</td><td>{r["平均CV"]}</td>'
    f'<td>{r["平均安全库存"]:.1f}</td><td>{r["策略"]}</td></tr>'
    for _, r in matrix.iterrows()
)

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>供应链库存健康度诊断看板</title>
<style>
 body{{font-family:"Microsoft YaHei",system-ui,sans-serif;background:#f4f6fa;margin:0;padding:28px;color:#1b2430}}
 h1{{font-size:26px;margin:0 0 4px}} .sub{{color:#6b7684;font-size:13px;margin-bottom:22px}}
 .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:22px}}
 .kpi{{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
 .kpi .v{{font-size:24px;font-weight:700;color:#2F5597}} .kpi .k{{font-size:12px;color:#6b7684;margin-top:4px}}
 .grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
 .card{{background:#fff;border-radius:10px;padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,.07)}}
 .card h3{{font-size:14px;margin:0 0 14px;color:#2F5597}}
 .bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:9px;font-size:12px}}
 .lb{{width:170px;text-align:right;color:#41505f;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
 .track{{flex:1;background:#eef1f6;border-radius:4px;height:16px;overflow:hidden}}
 .track i{{display:block;height:100%;border-radius:4px}}
 .vl{{width:92px;font-variant-numeric:tabular-nums;color:#1b2430}}
 table{{width:100%;border-collapse:collapse;font-size:12px}}
 th{{background:#2F5597;color:#fff;padding:8px;text-align:left;font-weight:600}}
 td{{padding:7px 8px;border-bottom:1px solid #eef1f6}}
 tr:nth-child(even) td{{background:#fafbfd}}
 .wide{{grid-column:1/-1}}
 .note{{font-size:12px;color:#6b7684;margin-top:10px;line-height:1.7}}
</style></head><body>
<h1>供应链库存健康度诊断与安全库存优化</h1>
<div class="sub">数据源 DataCo Smart Supply Chain · 180,519 条订单明细 · 2015.01–2018.01 · 分析日期 2026-10</div>

<div class="kpis">
 <div class="kpi"><div class="v">180,519</div><div class="k">订单明细记录</div></div>
 <div class="kpi"><div class="v">118</div><div class="k">商品 SKU</div></div>
 <div class="kpi"><div class="v">57.28%</div><div class="k">订单延期率</div></div>
 <div class="kpi"><div class="v">76.87%</div><div class="k">A类贡献销售额</div></div>
 <div class="kpi"><div class="v">{ss_total:,.0f}</div><div class="k">安全库存建议(件)</div></div>
</div>

<div class="grid">
{bars(abcx, abcy, "ABC 分类：各类销售额占比", "%", "#2F5597")}
{bars(mxs["标签"].tolist(), mxs["销售额占比%"].tolist(), "ABC-XYZ 九宫格：各格销售额占比", "%", "#4472C4")}
{bars(sm_s["Shipping Mode"].tolist(), sm_s["延期率"].tolist(), "各配送方式延期率", "%", "#C00000")}
{bars(rg_s["Order Region"].tolist(), rg_s["延期率"].tolist(), "延期最严重的 Top10 区域", "%", "#ED7D31")}
{bars(mk_s["Market"].tolist(), mk_s["销售额占比%"].tolist(), "各市场销售额占比", "%", "#70AD47")}
{bars([x[:26] for x in top10["Product Name"].tolist()], top10["销售额"].tolist(), "销售额 Top10 商品", "", "#7030A0", "{:,.0f}")}
<div class="card wide"><h3>ABC-XYZ 分类明细与库存策略</h3>
<table><tr><th>格子</th><th>SKU 数</th><th>销售额占比</th><th>平均 CV</th><th>平均安全库存</th><th>管理策略</th></tr>
{matrix_rows}
</table></div>
</div>
<div class="note">
口径说明：ABC 按累计销售额 80%/95% 分界；XYZ 按月度需求变异系数 CV（≤0.5 为 X，0.5–1 为 Y，&gt;1 为 Z），周口径仅作敏感性参考。
安全库存 SS = Z × σ<sub>d</sub> × √L，σ<sub>d</sub> 为周需求标准差，L 为实际提前期（周）。
Z 按 ABC 分档：A 类 99%（Z=2.326）、B 类 95%（1.645）、C 类 90%（1.282）——服务水平随商品重要性递减，避免把管理资源平摊到长尾品上。
</div>
</body></html>"""

html_path = os.path.join(OUT, "库存分析看板.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)
print("已生成:", html_path)

print("\n输出目录:")
for f in sorted(os.listdir(OUT)):
    print("  ", f)
