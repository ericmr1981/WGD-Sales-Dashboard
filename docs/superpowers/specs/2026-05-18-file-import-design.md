# 文件导入功能 — 设计文档

## 概述

在 Streamlit 商品销售分析报表的侧边栏中增加文件上传导入功能，支持将收银明细表和商品明细表直接通过网页界面上传到 Supabase，替代现有的 CLI 脚本。

## 交互设计

### 位置

侧边栏筛选器下方，用 `st.expander` 折叠，默认收起：

```
┌─────────────────────────┐
│  筛选器 (现有)           │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  ▼ 数据导入              │
│  ┌─────────────────────┐ │
│  │ ○ 收银明细表         │ │
│  │ ○ 商品明细表         │ │
│  │ [选择文件...]        │ │
│  │ [开始导入]           │ │
│  └─────────────────────┘ │
└─────────────────────────┘
```

### 流程

```
1. 用户选择文件类型 radio（收银明细表 / 商品明细表）
2. 上传文件（限制 xlsx / csv）
3. 点击"开始导入"
4. 系统解析文件 → 查询 Supabase 已有数据 → 比对重复
5. 展示预览："200 条新记录待导入，300 条已存在跳过"
6. 用户点击"确认导入"
7. 分批上传 → 显示进度 → 完成 → st.rerun() 自动刷新
```

## 新增模块

### import_utils.py

位于项目根目录，与 db.py / queries.py 同级。

| 函数 | 说明 |
|------|------|
| `parse_pos_orders(file_bytes)` | 解析收银明细表 XLSX → list[dict] |
| `parse_product_sales(file_bytes)` | 解析商品明细表 CSV → list[dict] |
| `find_existing_orders(conn, order_nos)` | 查询已存在的 order_no 集合 |
| `find_existing_items(conn, items)` | 查询已存在的 (order_no, product_name) 集合 |
| `upload_batch(table, rows)` | 分批 POST 到 Supabase |

### 解析规则

**收银明细表 XLSX（pos_orders）：**
- 列索引和 import_pos.py 一致（列 A-P，行 3+）
- 支付渠道列映射：yunshanfu, wechat_pay, alipay, cash, douyin_coupon, meituan_coupon, free_payment, custom_payment
- 去重键：order_no

**商品明细表 CSV（product_sales）：**
- 中文列头：商品名称 / 日期 / 订单号 / 商品原价 / 销售数量 / 商品销售额 / 商品实收 / 商品优惠
- 编码：utf-8-sig
- 跳过商品名称为 "--" 的行
- 去重键：(order_no, product_name) 组合

### Supabase 上传

- 复用 `db.py` 的 `_get_supabase_config()` 获取凭证
- 使用直接 HTTP 请求（与现有代码一致的 SSL workaround）
- POST 时带 `Prefer: resolution=merge-duplicates` 头
- 每批 500 条

### 错误处理

| 场景 | 处理 |
|------|------|
| 文件格式不匹配（缺必要列） | st.error() 显示具体缺失列名 |
| 网络错误 | 显示失败条数和错误信息 |
| 解析异常（非标准格式） | 捕获异常，显示行号和原因 |
| 空文件 | 提示无有效数据 |

### app.py 改动

1. 导入 `import_utils` 模块
2. 侧边栏末尾增加 `st.divider()` + `st.expander("数据导入")`
3. expander 内放 radio 选择类型、file_uploader、导入按钮
4. 导入完成后 `st.rerun()` 刷新数据
