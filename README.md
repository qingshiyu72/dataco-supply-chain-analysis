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
按需求变异系数 CV = σ/μ 分档：CV ≤ 0.5 为 X（稳定）、0.5–1.0 为 Y（波动）、>1.0 为 Z（剧烈波动）。目的是识别哪些 SKU 难以预测、需要更高缓冲。

**ABC-XYZ 九宫格**
两个维度交叉形成 9 种组合，每种组合对应不同的库存策略。

**安全库存模型**

$$SS = Z \times \sigma_d \times \sqrt{L}$$

$$ROP = \bar{d} \times L + SS$$

| 参数 | 取值 | 说明 |
|---|---|---|
| Z | 1.65 | 对应 95% 服务水平 |
| σ_d | 周需求标准差 | 需求波动性 |
| L | 实际提前期（周） | 取自 `Days for shipping (real)` |

## 四、关键发现

| # | 发现 | 数据支撑 |
|---|---|---|
| 1 | **帕累托效应显著** | 7 个 SKU（占 5.93%）贡献 **76.87%** 销售额 |
| 2 | **履约严重失效** | 延期订单占比 **57.28%**，平均延期 1.62 天 |
| 3 | **延期根因是承诺设定而非执行能力** | First Class 延期率 **100%**（承诺 1 天/实际 2 天）；Standard Class 仅 **39.8%** |
| 4 | **长尾 SKU 管理低效** | 51 个 C-Z 类 SKU（占 43%）仅贡献 **2.03%** 销售额，CV 高达 3.591 |
| 5 | **区域差异极小** | 各市场延期率均在 56.8%–57.7%，说明是系统性问题而非区域性问题 |

### 最值得关注的两个格子

- **A-X（7 个 SKU / 76.87% 销售额 / CV 0.353）**：最重要且最稳定，可 JIT 低库存运营
- **C-Z（51 个 SKU / 2.03% 销售额 / CV 3.591）**：占 43% 的 SKU 数量却几乎不贡献价值，应考虑淘汰或合并

## 五、项目结构

```
dataco-supply-chain-analysis/
├── data/                      # 原始数据（不入 Git，见 .gitignore）
│   ├── DataCoSupplyChainDataset.csv        # 主表 180,519 × 53（约 91MB）
│   └── DescriptionDataCoSupplyChain.csv    # 官方字段字典（53 个字段说明）
├── src/
│   ├── 01_pipeline.py      # 主分析管线（清洗→画像→ABC→XYZ→安全库存→履约诊断）
│   ├── 02_xyz_dual.py      # XYZ 双口径（周/月）交叉验证
│   └── 03_report.py        # 生成 Excel 报告与 HTML 看板
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
│   └── 08_XYZ双口径对比.csv
├── .gitignore                # 排除大体积数据文件
└── README.md
```

## 六、复现方式

```bash
pip install pandas numpy openpyxl

# 1. 下载数据到 data/ 目录（见上方「二、数据源」）
#    需要两个文件：
#      data/DataCoSupplyChainDataset.csv
#      data/DescriptionDataCoSupplyChain.csv

# 2. 依次运行
python src/01_pipeline.py    # 主分析管线
python src/02_xyz_dual.py    # XYZ 双口径验证
python src/03_report.py      # 生成报告与看板
```

脚本使用相对路径（基于项目根目录自动定位 `data/`），**克隆后无需修改任何路径即可运行**。

## 七、技术栈

- **Python** — pandas / numpy 数据处理与统计分析
- **Excel 自动化** — openpyxl 生成带原生图表的报告
- **统计方法** — 帕累托分析、变异系数、正态分布服务水平、安全库存模型

## 八、局限与展望

**数据层面的局限：**

1. **缺少真实在库数量** — 数据只有订单流向，无库存快照，因此库存周转率只能用订单频次近似，无法精确计算
2. **提前期字段为发货口径** — `Days for shipping` 反映的是发货时长，不是完整的采购提前期
3. **数据时效性** — 数据为 2015–2018 年，需求模式可能已发生变化

**方法层面的局限：**

1. **服务水平为假设值** — Z=1.65（95%）为行业惯例，实际应根据 SKU 重要性差异化设定（A 类可到 99%，C 类 90% 即可）
2. **CV 口径敏感性** — 周口径与月口径下 XYZ 分类存在差异（Z 类 87 vs 60），本项目采用月口径，但结论对该选择有一定依赖
3. **未考虑相关性** — 各 SKU 需求独立假设，实际可能存在替代或互补关系

**后续可拓展方向：**

- 结合 `tokenized_access_logs.csv` 访问日志做非结构化数据分析
- 引入时间序列模型（ARIMA / Prophet）替代简化的正态假设
- 增加 EOQ 计算，形成完整的（s, S）库存策略
- 构建库存健康度评分卡，实现 SKU 级自动预警

---

*本项目所有分析结论均基于公开数据，代码可复现。*
