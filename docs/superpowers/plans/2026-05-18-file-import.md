# 文件导入功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a file upload interface in the sidebar to import 收银明细表 (XLSX → pos_orders) and 商品明细表 (CSV → product_sales) directly into Supabase.

**Architecture:** New `import_utils.py` module handles parsing (XLSX via openpyxl, CSV via csv.DictReader) and Supabase upload (direct HTTP, same pattern as db.py). `app.py` sidebar gets an expander with radio type selector, file uploader, and a two-stage flow (preview duplicates → confirm import → rerun).

**Tech Stack:** openpyxl (already in env via import_pos.py), csv, urllib.request (existing Supabase pattern), streamlit

---

### Task 1: Create import_utils.py — Parsing + Upload Module

**Files:**
- Create: `import_utils.py`
- Reference: `supabase_setup/import_pos.py` (XLSX parsing logic)
- Reference: `supabase_setup/data_import.py` (CSV parsing logic)
- Reference: `db.py` (Supabase config and HTTP pattern)

- [ ] **Step 1: Write the module with pos_orders parsing**

```python
"""File import utilities: parse XLSX/CSV and upload to Supabase."""
import csv
import json
import ssl
import io
import urllib.request
from typing import List, Optional

import openpyxl

from db import _get_supabase_config

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def clean_value(val):
    if val is None:
        return None
    val = str(val).strip().strip("`").strip("'")
    return val if val else None


def _supabase_request(method: str, path: str, data: Optional[list] = None):
    supabase_url, supabase_key = _get_supabase_config()
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured.")
    url = f"{supabase_url}/rest/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("apikey", supabase_key)
    req.add_header("Authorization", f"Bearer {supabase_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if method == "POST":
        req.add_header("Prefer", "resolution=merge-duplicates")
    try:
        resp = urllib.request.urlopen(req, context=_ctx)
        raw = resp.read().decode()
        return json.loads(raw) if raw else []
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409:
            return None
        raise RuntimeError(f"Supabase HTTP {e.code}: {body[:200]}")
    except Exception as e:
        raise RuntimeError(f"Supabase request failed: {e}")


def parse_pos_orders(file_bytes: bytes) -> List[dict]:
    """Parse 收银明细表 XLSX → list of row dicts for pos_orders table."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active

    def _col(n):
        v = ws.cell(row_idx, n).value
        return float(v) if v is not None else 0.0

    rows = []
    seen = set()
    for row_idx in range(3, ws.max_row + 1):
        order_no = clean_value(ws.cell(row_idx, 3).value)
        if not order_no or order_no in seen:
            continue
        seen.add(order_no)
        rows.append({
            "order_no": order_no,
            "store_name": clean_value(ws.cell(row_idx, 1).value),
            "sale_date": clean_value(ws.cell(row_idx, 2).value),
            "total_revenue": _col(4),
            "gross_income": _col(5),
            "discount_total": _col(6),
            "net_revenue": _col(7),
            "quantity": int(_col(8)),
            "yunshanfu": _col(9),
            "free_payment": _col(10),
            "wechat_pay": _col(11),
            "douyin_coupon": _col(12),
            "alipay": _col(13),
            "cash": _col(14),
            "meituan_coupon": _col(15),
            "custom_payment": _col(16),
        })
    return rows
```

- [ ] **Step 2: Add product_sales parsing**

Append to `import_utils.py`:

```python
def parse_product_sales(file_bytes: bytes) -> List[dict]:
    """Parse 商品明细表 CSV → list of row dicts for product_sales table."""
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        name = clean_value(row.get("商品名称", ""))
        if not name or name == "--":
            continue
        rows.append({
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
    return rows
```

- [ ] **Step 3: Add duplicate-checking and upload functions**

Append to `import_utils.py`:

```python
def check_existing_orders(order_nos: List[str]) -> set:
    """Query Supabase for which order_nos already exist in pos_orders."""
    if not order_nos:
        return set()
    result = _supabase_request("GET", f"pos_orders?select=order_no&order_no=in.({','.join(order_nos)})")
    return {r["order_no"] for r in result if r.get("order_no")}


def check_existing_product_sales(keys: List[tuple]) -> set:
    """Query Supabase for which (order_no, product_name) pairs already exist.
    
    Keys is a list of (order_no, product_name) tuples.
    Since Supabase doesn't support composite IN queries easily,
    we batch all order_nos and match in-memory.
    """
    if not keys:
        return set()
    order_nos = list({k[0] for k in keys})
    result = _supabase_request(
        "GET",
        f"product_sales?select=order_no,product_name&order_no=in.({','.join(order_nos)})"
    )
    existing = {(r["order_no"], r["product_name"]) for r in result if r.get("order_no") and r.get("product_name")}
    return existing


def upload_batch(table: str, rows: List[dict]) -> int:
    """Upload rows to Supabase table in batches of 500. Returns count of uploaded rows."""
    total = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        _supabase_request("POST", table, chunk)
        total += len(chunk)
    return total
```

- [ ] **Step 4: Commit**

```bash
git add import_utils.py
git commit -m "feat: add import_utils module for file parsing and Supabase upload"
```

---

### Task 2: Add Upload UI to Sidebar

**Files:**
- Modify: `app.py` (sidebar section, after existing filters)

- [ ] **Step 1: Add import at top of app.py**

Insert after existing imports in `app.py`:

```python
from import_utils import parse_pos_orders, parse_product_sales, check_existing_orders, check_existing_product_sales, upload_batch
```

- [ ] **Step 2: Add import UI section to sidebar**

Insert at end of sidebar block, after the existing filter widgets (after `st.selectbox` for channels, before the `df_str = ...` line):

```python
# ========== 数据导入 ==========
st.sidebar.divider()
with st.sidebar.expander(":material/upload: 数据导入", expanded=False):
    import_type = st.radio(
        "文件类型",
        ["收银明细表", "商品明细表"],
        key="import_type",
        label_visibility="collapsed",
    )
    uploaded_file = st.file_uploader(
        "选择文件",
        type=["xlsx"] if import_type == "收银明细表" else ["csv"],
        key="import_file",
    )

    if uploaded_file and "import_state" not in st.session_state:
        if st.button("解析文件"):
            with st.spinner("正在解析..."):
                try:
                    file_bytes = uploaded_file.getvalue()
                    if import_type == "收银明细表":
                        rows = parse_pos_orders(file_bytes)
                    else:
                        rows = parse_product_sales(file_bytes)
                except Exception as e:
                    st.error(f"解析失败: {e}")
                    st.stop()

                if not rows:
                    st.warning("文件中没有有效数据")
                    st.stop()

                # Check duplicates
                with st.spinner("正在检查重复..."):
                    try:
                        if import_type == "收银明细表":
                            existing = check_existing_orders([r["order_no"] for r in rows])
                            new_rows = [r for r in rows if r["order_no"] not in existing]
                            dup_count = len(rows) - len(new_rows)
                        else:
                            keys = [(r["order_no"], r["product_name"]) for r in rows]
                            existing = check_existing_product_sales(keys)
                            new_rows = [r for r in rows if (r["order_no"], r["product_name"]) not in existing]
                            dup_count = len(rows) - len(new_rows)
                    except Exception as e:
                        st.error(f"检查重复失败: {e}")
                        st.stop()

                if not new_rows:
                    st.info("所有记录均已存在，无需导入")
                    st.stop()

                st.session_state.import_new_rows = new_rows
                st.session_state.import_total = len(rows)
                st.session_state.import_dup = dup_count
                st.session_state.import_table = "pos_orders" if import_type == "收银明细表" else "product_sales"
                st.rerun()

    # Show preview and confirm after parsing
    if "import_new_rows" in st.session_state:
        new_rows = st.session_state.import_new_rows
        st.caption(f"待导入: {len(new_rows)} 条 | 跳过重复: {st.session_state.import_dup} 条")
        if import_type == "收银明细表":
            st.dataframe(
                [{k: r[k] for k in ["order_no", "sale_date", "total_revenue", "net_revenue"]} for r in new_rows[:5]],
                height=150,
            )
        else:
            st.dataframe(
                [{k: r[k] for k in ["order_no", "product_name", "quantity", "total_price"]} for r in new_rows[:5]],
                height=150,
            )

        if st.button("确认导入"):
            with st.spinner(f"正在导入 {len(new_rows)} 条记录..."):
                try:
                    count = upload_batch(st.session_state.import_table, new_rows)
                    st.success(f"成功导入 {count} 条记录")
                    # Clear state and refresh
                    for key in ["import_new_rows", "import_total", "import_dup", "import_table"]:
                        del st.session_state[key]
                    st.rerun()
                except Exception as e:
                    st.error(f"导入失败: {e}")

        if st.button("取消"):
            for key in ["import_new_rows", "import_total", "import_dup", "import_table"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add file upload interface to sidebar for data import"
```

---

### Task 3: Clean Up Legacy Import Scripts (optional)

**Files:**
- Remove: `supabase_setup/data_import.py` (replaced by import_utils.py)
- Remove: `supabase_setup/run_import.py` (replaced by import_utils.py)

Optional — user can keep CLI fallback scripts if desired.

- [ ] **Step 1: Verify import_utils.py covers all needed functionality**
- [ ] **Step 2: Remove obsolete files (if desired)**

```bash
git rm supabase_setup/data_import.py supabase_setup/run_import.py
git commit -m "chore: remove legacy import scripts replaced by import_utils.py"
```

---

### Verification

1. Manual test: Open sidebar expander "数据导入", select 收银明细表, upload an XLSX file, verify preview shows new vs duplicate count, confirm import, verify dashboard refreshes with new data
2. Manual test: Same flow for 商品明细表 CSV
3. Manual test: Upload a file with all existing records, verify "所有记录均已存在" message
4. Manual test: Upload an invalid file format, verify error message
5. Manual test: Cancel import mid-flow, verify state resets cleanly
