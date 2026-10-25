# 供应链库存健康度诊断与安全库存优化

> Supply Chain Inventory Health Diagnosis & Safety Stock Optimization

基于 **180,519 条真实供应链订单数据**，用 ABC-XYZ 分类法诊断 118 个 SKU 的库存健康状况，并计算每个 SKU 的安全库存与再订货点，输出差异化管理策略。

---

## 一、项目背景

库存管理存在一个根本矛盾：

- **库存过多** → 占用资金、产生仓储成本、面临贬值风险
- **库存过少** → 缺货、客户流失、销售损失

本项目要回答的核心问题是：**在有限的资金和管理资源下，如何为每个 SKU 设定合理的库存水位？**

## 二、数据源

| 项目 | 说明 |
|---|---|
| 数据集 | [DataCo Smart Supply Chain](https://tianchi.aliyun.com/dataset/92708) |
| 规模 | 180,519 条订单明细 × 53 个字段 |
| 时间跨度 | 2015-01 至 2018-01 |
| 覆盖范围 | 118 个 SKU、5 大市场、23 个区域 |
| 编码 | latin-1（读取时需指定） |

主要使用字段：

- `Sales` / `Order Profit Per Order` — 价值维度
- `Order Item Quantity` — 需求量
- `order date (DateOrders)` — 时间维度
- `Days for shipping (real)` / `Days for shipment (scheduled)` — 提前期与履约
- `Product Name` / `Category Name` / `Department Name` — 商品维度
- `Order Region` / `Market` — 地理维度

## 三、分析方法

### 3.1 整体框架

```
数据清洗 → 特征工程 → ABC 分类（价值）→ XYZ 分类（波动性）
    → 九宫格策略矩阵 → 安全库存/再订货点 → 履约诊断
```

### 3.2 核心方法说明

**ABC 分类（帕累托分析）**
按销售额降序累计，累计占比 ≤80% 为 A 类、80%–95% 为 B 类、>95% 为 C 类。目的是把管理资源按价值贡献分配。

**XYZ 分类（需求波动性）**
按月度需求变异系数 CV = σ/μ 分档：CV ≤ 0.5 为 X（稳定）、0.5–1.0 为 Y（波动）、>1.0 为 Z（剧烈波动）。目的是识别哪些 SKU 难以预测、需要更高缓冲。周口径另算一遍作敏感性参考（`08_XYZ双口径对比.csv`）。

**ABC-XYZ 九宫格**
两个维度交叉形成 9 种组合，每种组合对应不同的库存策略。

**安全库存模型**

$$SS = Z \times \sigma_d \times \sqrt{L}$$

$$ROP = \bar{d} \times L + SS$$

| 参数 | 取值 | 说明 |
|---|---|---|
| Z | A 类 2.326 / B 类 1.645 / C 类 1.282 | 分别对应 99% / 95% / 90% 服务水平，**按 ABC 分档** |
| σ_d | 周需求标准差 | 需求波动性 |
| L | 实际提前期（周） | 取自 `Days for shipping (real)` |

**为什么 Z 要分档**：服务水平每提一档，安全库存按 Z 值比例上升、资金占用随之上升。全线用 95% 等于给"贡献 5% 销售额的长尾品"和"贡献 77% 的头部品"同样待遇，把管理资源平摊掉了，与 ABC 分类的初衷矛盾。分档后 118 个 SKU 的安全库存合计从 1,777 件（统一 95%）变为 1,922 件（+8.2%），但**结构**变了：A 类拿到的库存份额从 36.1% 升到 47.2%，而 A 类贡献 76.9% 的销售额。

## 四、关键发现

| # | 发现 | 数据支撑 |
|---|---|---|
| 1 | **帕累托效应显著** | 7 个 SKU（占 5.93%）贡献 **76.87%** 销售额 |
| 2 | **履约严重失效** | 延期订单占比 **57.28%**，平均延期 1.62 天 |
| 3 | **延期根因是承诺设定而非执行能力** | First Class 延期率 **100%**（承诺 1 天/实际 2 天）；Standard Class 仅 **39.8%** |
| 4 | **长尾 SKU 管理低效** | 53 个 C-Z 类 SKU（占 SKU 44.9%）仅贡献 **2.08%** 销售额，平均 CV 3.626 |
| 5 | **区域差异极小** | 各市场延期率均在 56.8%–57.7%，说明是系统性问题而非区域性问题 |

### 最值得关注的两个格子

- **A-X（7 个 SKU / 76.87% 销售额 / CV 0.353）**：最重要且最稳定，安全库存平均只需 0.61 周需求量，可 JIT 低库存运营
- **C-Z（53 个 SKU / 44.9% 的 SKU 数量 / 2.08% 销售额 / CV 3.626）**：占近一半 SKU 却几乎不贡献价值，应考虑淘汰或合并

> 注：9 个格子中实测只有 6 格非空——C-X、A-Y、A-Z 没有 SKU 落入。C 类里没有稳定品，A 类里没有波动品，这个结构性事实本身比"九宫格齐满"更值得说。

## 五、项目结构

```
dataco-supply-chain-analysis/
├── data/                      # 原始数据（不入 Git，见 .gitignore）
│   ├── DataCoSupplyChainDataset.csv        # 主表 180,519 × 53（约 91MB）
│   ├── DescriptionDataCoSupplyChain.csv    # 官方字段字典（53 个字段说明）
│   └── supplychain.db                      # 由 00 脚本生成的 SQLite 库（不入 Git）
├── src/
│   ├── 00_build_db.py     # 建 SQLite 库 + 用窗口函数做 ABC 分类 + 与 pandas 交叉校验
│   ├── 01_pipeline.py     # 主分析管线（清洗→画像→ABC→XYZ→安全库存→履约诊断）
│   ├── 02_xyz_dual.py     # XYZ 双口径（周/月）独立复算与敏感性对比
│   ├── 03_report.py       # 生成 Excel 报告与 HTML 看板
│   └── 04_data_validation.py  # 订单明细规则校验（等价类 / 边界值 / 口径一致性）
├── outputs/
│   ├── 供应链库存分析报告.xlsx    # 5 个 Sheet + 原生图表
│   ├── 库存分析看板.html         # 可视化看板
│   ├── 00_字段画像.csv
│   ├── 01_商品主表_含ABCXYZ.csv  # 118 个 SKU 完整分析结果
│   ├── 02_ABC统计.csv
│   ├── 03_XYZ统计.csv
│   ├── 04_ABC_XYZ矩阵.csv
│   ├── 05_配送方式履约.csv
│   ├── 06_市场履约.csv
│   ├── 07_区域履约.csv
│   ├── 08_XYZ双口径对比.csv
│   └── 09_SQL_ABC校验.csv        # SQL 口径的累计占比与档位（逐 SKU）
├── .gitignore                # 排除大体积数据文件
├── README.md
└── 数据校验方案与实测报告.md   # 校验规则设计与实测结论（对应 src/04）
```

**关于 SQLite**：180,519 行明细灌进 `order_items` 表并按 `Product Name` 建索引，ABC 的"按销售额降序 + 累计占比"用窗口函数一次算完：

```sql
SUM(sales) OVER (ORDER BY sales DESC
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
  * 1.0 / SUM(sales) OVER () AS cum_share
```

同一张表用 pandas `cumsum` 再算一遍作交叉校验，`09_SQL_ABC校验.csv` 是逐 SKU 的结果，两套实现 **118/118 完全一致**。

## 六、复现方式

```bash
pip install pandas numpy openpyxl

# 1. 下载数据到 data/ 目录（见上方「二、数据源」）
#    需要两个文件：
#      data/DataCoSupplyChainDataset.csv
#      data/DescriptionDataCoSupplyChain.csv

# 2. 依次运行
python src/00_build_db.py    # 建 SQLite 库 + SQL 版 ABC + 交叉校验
python src/01_pipeline.py    # 主分析管线（主口径由这里产出）
python src/02_xyz_dual.py    # XYZ 双口径独立复算与敏感性对比
python src/03_report.py      # 生成报告与看板
python src/04_data_validation.py   # 可选：原始明细规则校验（结论见「数据校验方案与实测报告」）
```

脚本使用相对路径（基于项目根目录自动定位 `data/`），**克隆后无需修改任何路径即可运行**。
仅 01 会写 `01_商品主表` / `03_XYZ统计` / `04_ABC_XYZ矩阵`；02 只输出 `08_XYZ双口径对比.csv`，不覆盖主口径，因此**脚本顺序不影响结果**（重复运行结果一致）。

## 七、技术栈

- **SQL** — SQLite 建库与索引、窗口函数（`SUM() OVER`、`ROW_NUMBER()`）做累计占比与排名
- **Python** — pandas / numpy 数据处理与统计分析
- **Excel 自动化** — openpyxl 生成带原生图表的报告
- **统计方法** — 帕累托分析、变异系数、正态分布服务水平、安全库存模型

## 八、局限与展望

**数据层面的局限：**

1. **缺少真实在库数量** — 数据只有订单流向，无库存快照，因此库存周转率只能用订单频次近似，无法精确计算
2. **提前期字段为发货口径** — `Days for shipping` 反映的是发货时长，不是完整的采购提前期
3. **数据时效性** — 数据为 2015–2018 年，需求模式可能已发生变化

**方法层面的局限：**

1. **服务水平的档位是行业惯例，不是最优解** — 99 / 95 / 90 三档取自通用的缺货成本经验值；严格做法是用缺货损失与持货成本反推每个 SKU 的最优服务水平
2. **CV 口径敏感性** — 周口径与月口径下 XYZ 分类差异明显（Z 类 91 vs 64），差异全部集中在 Z→Y：27 个商品在周粒度上"多数周没订单、靠补 0 撑高标准差"，落到月粒度就回落成 Y。本项目以月口径为主（更接近实际计划周期），结论对该选择有依赖
3. **未考虑相关性** — 各 SKU 需求独立假设，实际可能存在替代或互补关系

**后续可拓展方向：**

- 结合 `tokenized_access_logs.csv` 访问日志做非结构化数据分析
- 引入时间序列模型（ARIMA / Prophet）替代简化的正态假设
- 增加 EOQ 计算，形成完整的（s, S）库存策略
- 构建库存健康度评分卡，实现 SKU 级自动预警

---

*本项目所有分析结论均基于公开数据，代码可复现。*
