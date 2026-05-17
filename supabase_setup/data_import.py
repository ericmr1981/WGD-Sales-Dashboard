import csv
import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_value(val):
    """清理反引号和空白"""
    if val is None:
        return None
    val = val.strip().strip("`").strip("'")
    return val if val else None


def import_payments():
    filepath = os.path.join(BASE_DIR, "支付数据 明细数据.csv")
    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            batch.append({
                "order_no": clean_value(row.get("订单编号", "")),
                "payment_time": clean_value(row.get("日期", "")),
                "channel": clean_value(row.get("渠道", "")),
                "merchant_id": clean_value(row.get("商户号", "")),
                "store_id": clean_value(row.get("门店id", "")),
                "store_name": clean_value(row.get("入账门店", "")),
                "receipt_type": clean_value(row.get("收款类型", "")),
                "order_type": clean_value(row.get("订单类型", "")),
                "order_store": clean_value(row.get("下单门店", "")),
                "payment_serial": clean_value(row.get("支付流水号", "")),
                "transaction_id": clean_value(row.get("交易号", "")),
                "business_type": clean_value(row.get("业务类型", "")),
                "total_amount": float(clean_value(row.get("交易额", "0")) or 0),
                "income_amount": float(clean_value(row.get("收入金额(元)", "0")) or 0),
                "merchant_discount": float(clean_value(row.get("商家优惠金额", "0")) or 0),
                "platform_discount": float(clean_value(row.get("平台优惠金额", "0")) or 0),
                "refund_amount": float(clean_value(row.get("退款金额", "0")) or 0),
                "service_fee": float(clean_value(row.get("服务费", "0")) or 0),
                "coupon_name": clean_value(row.get("优惠名称", "")),
            })
    # 分批插入，跳过重复 order_no 的记录
    success = 0
    for i in range(0, len(batch), 500):
        chunk = batch[i:i + 500]
        try:
            supabase.table("payments").insert(chunk).execute()
            success += len(chunk)
            print(f"  payments: 已导入 {success}/{len(batch)} 条")
        except Exception as e:
            # 批量失败时逐条插入，跳过重复
            for row in chunk:
                try:
                    supabase.table("payments").insert(row).execute()
                    success += 1
                except Exception:
                    pass  # 跳过重复 order_no
            print(f"  payments: 已导入 {success}/{len(batch)} 条（逐条模式）")
    print(f"payments 导入完成，成功 {success}/{len(batch)} 条")


def import_product_sales():
    filepath = os.path.join(BASE_DIR, "商品销售明细表 2026年4月 (1).csv")
    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            name = clean_value(row.get("商品名称", ""))
            if name == "--":
                continue
            batch.append({
                "store_name": clean_value(row.get("门店名称", "")),
                "sale_date": clean_value(row.get("日期", "")),
                "order_no": clean_value(row.get("订单号", "")),
                "product_name": name,
                "unit_price": float(clean_value(row.get("商品原价", "0")) or 0),
                "quantity": int(float(clean_value(row.get("销售数量", "1")) or 1)),
                "total_price": float(clean_value(row.get("商品销售额", "0")) or 0),
                "actual_received": float(clean_value(row.get("商品实收", "0")) or 0),
                "discount": float(clean_value(row.get("商品优惠", "0")) or 0),
            })
    for i in range(0, len(batch), 500):
        chunk = batch[i:i + 500]
        supabase.table("product_sales").insert(chunk).execute()
        print(f"  product_sales: 已导入 {min(i+500, len(batch))}/{len(batch)} 条")
    print(f"product_sales 导入完成，共 {len(batch)} 条")


if __name__ == "__main__":
    print("开始导入 payments...")
    import_payments()
    print("开始导入 product_sales...")
    import_product_sales()
    print("全部导入完成！")
