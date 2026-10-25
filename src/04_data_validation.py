"""数据校验：对 DataCo 供应链订单明细执行规则校验。

规则来源见 ../数据校验方案与实测报告.md
用法：python src/04_data_validation.py [csv路径]
"""
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime

DEFAULT = "data/DataCoSupplyChainDataset.csv"
FMT = "%m/%d/%Y %H:%M"

STATUS = {"COMPLETE", "PENDING_PAYMENT", "PROCESSING", "PENDING", "CLOSED",
          "ON_HOLD", "SUSPECTED_FRAUD", "CANCELED", "PAYMENT_REVIEW"}
DELIVERY = {"Late delivery", "Advance shipping", "Shipping on time", "Shipping canceled"}
SHIP_MODE = {"Standard Class", "Second Class", "First Class", "Same Day"}

KEY_FIELDS = ["Order Id", "Order Item Id", "Order Item Cardprod Id",
              "Customer Id", "Order Item Quantity", "Sales"]


def run(path):
    fails = Counter()
    samples = defaultdict(list)
    seen_item = set()
    order_customer = {}
    order_date = {}
    product_name = {}
    category_name = {}
    total_by_order = defaultdict(float)
    dates = []
    rows = 0

    def fail(rule, detail):
        fails[rule] += 1
        if len(samples[rule]) < 2:
            samples[rule].append(detail)

    with open(path, "r", encoding="latin-1", newline="") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            item_id = row["Order Item Id"]
            order_id = row["Order Id"]

            # 1 主键唯一
            if item_id in seen_item:
                fail("1.主键重复", item_id)
            seen_item.add(item_id)

            # 2 关键字段非空
            for k in KEY_FIELDS:
                if not row[k].strip():
                    fail("2.关键字段为空", "%s/%s" % (item_id, k))

            # 3 数量为 1-5 的整数
            try:
                qty = float(row["Order Item Quantity"])
                if qty != int(qty) or not 1 <= qty <= 5:
                    fail("3.数量越界", "%s=%s" % (item_id, qty))
            except ValueError:
                fail("3.数量非数值", item_id)

            # 4 日期可解析且在范围内，且不早于下单
            try:
                order_dt = datetime.strptime(row["order date (DateOrders)"], FMT)
                dates.append(order_dt)
                if order_dt < datetime(2015, 1, 1) or order_dt.date() > datetime(2018, 1, 31).date():
                    fail("4.下单日期越界", "%s=%s" % (item_id, order_dt))
                ship_raw = row["shipping date (DateOrders)"].strip()
                if ship_raw:
                    ship_dt = datetime.strptime(ship_raw, FMT)
                    if ship_dt < order_dt:
                        fail("4.发货早于下单", "%s=%s<%s" % (item_id, ship_dt, order_dt))
            except ValueError:
                fail("4.日期格式异常", item_id)
                order_dt = None

            # 5 枚举值
            if row["Order Status"] not in STATUS:
                fail("5.订单状态非法", row["Order Status"])
            if row["Delivery Status"] not in DELIVERY:
                fail("5.配送状态非法", row["Delivery Status"])
            if row["Shipping Mode"] not in SHIP_MODE:
                fail("5.配送方式非法", row["Shipping Mode"])

            # 6 行级乘积关系：Sales = 单价 × 数量
            try:
                unit = float(row["Order Item Product Price"])
                sales = float(row["Sales"])
                if abs(unit * qty - sales) > 0.02:
                    fail("6.销售额不等于单价乘数量", "%s %.2f*%s!=%.2f" % (item_id, unit, qty, sales))

                # 7 折扣关系：Total = Sales × (1 - 折扣率)，容差 1%
                total = float(row["Order Item Total"])
                rate = float(row["Order Item Discount Rate"])
                if total > 0 and abs(sales * (1 - rate) - total) / total > 0.01:
                    fail("7.明细额与折扣不符", "%s" % item_id)
                if not 0 <= rate <= 0.25:
                    fail("7.折扣率越界", "%s=%s" % (item_id, rate))
                total_by_order[order_id] += total
            except ValueError:
                fail("6.金额字段非数值", item_id)

            # 8 维度一致性
            pid, pname = row["Product Card Id"], row["Product Name"]
            if pid in product_name and product_name[pid] != pname:
                fail("8.同一SKU名称不一致", pid)
            product_name.setdefault(pid, pname)

            cid, cname = row["Category Id"], row["Category Name"]
            if cid in category_name and category_name[cid] != cname:
                fail("8.同一品类名称不一致", cid)
            category_name.setdefault(cid, cname)

            # 9 同一订单的客户与日期应一致
            if order_id in order_customer and order_customer[order_id] != row["Customer Id"]:
                fail("9.同单客户不一致", order_id)
            order_customer.setdefault(order_id, row["Customer Id"])
            if order_dt is not None:
                if order_id in order_date and order_date[order_id] != order_dt.date():
                    fail("9.同单下单日期不一致", order_id)
                order_date.setdefault(order_id, order_dt.date())

    # 10 空表 / 单行边界
    if rows == 0:
        fail("10.数据集为空", "0 rows")
    elif rows == 1:
        fail("10.仅一行数据", "1 row")

    return rows, len(seen_item), len(order_customer), fails, samples, dates


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    rows, uniq_items, orders, fails, samples, dates = run(path)

    print("=" * 52)
    print("数据校验报告")
    print("=" * 52)
    print("总行数 %d | 唯一明细 %d | 订单数 %d" % (rows, uniq_items, orders))
    if dates:
        print("下单日期范围 %s ~ %s" % (min(dates), max(dates)))
    print()

    if not fails:
        print("全部校验通过")
    else:
        print("发现 %d 类问题：" % len(fails))
        for rule in sorted(fails):
            print("  %-24s %6d 条   例: %s" % (rule, fails[rule], " / ".join(samples[rule])))
    print()
    print("提示：利润类字段为行级，汇总请按行求和，不要按订单去重。")


if __name__ == "__main__":
    main()
