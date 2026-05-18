"""Import CSV data to Supabase using upsert with merge-duplicates."""
import csv
import os
import json
import urllib.request
import ssl

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SSL context for insecure mode
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def supabase_request(method, path, data=None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if method == "POST":
        req.add_header("Prefer", "resolution=merge-duplicates")
    try:
        resp = urllib.request.urlopen(req, context=ctx)
        raw = resp.read().decode()
        if raw:
            return json.loads(raw)
        return []
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409:
            return None
        print(f"  HTTP {e.code}: {body[:200]}")
        return None
    except Exception as e:
        print(f"  请求失败: {e}")
        return None


def clean_value(val):
    if val is None:
        return None
    val = val.strip().strip("`").strip("'")
    return val if val else None


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

    print(f"product_sales: 共 {len(batch)} 条")
    for i in range(0, len(batch), 500):
        chunk = batch[i:i + 500]
        supabase_request("POST", "product_sales", chunk)
        print(f"  product_sales: 已导入 {min(i+500, len(batch))}/{len(batch)}")
    print(f"product_sales: 完成，共 {len(batch)} 条")


if __name__ == "__main__":
    print("开始导入 product_sales...")
    import_product_sales()
    print()
    print("全部导入完成！")
