# 商品销售分析报表 — 设计文档

## 概述

基于 WGD 门店 2026年4月的支付数据和商品销售明细，构建一个商品销售分析报表。后端使用 Supabase 存储数据，前端使用 Streamlit 进行可视化展示。

## 数据源

两张 CSV 表通过 `订单号`（order_no）关联：

| 表名 | 行数 | 内容 |
|------|------|------|
| 支付数据 明细数据.csv | 784 | 每笔支付的渠道、金额、时间、退款等 |
| 商品销售明细表 2026年4月 (1).csv | 2,796 | 每单每个商品的名称、数量、价格、优惠 |

## 架构方案（已确认）

**方案 C：两张原始表 + Supabase View**

- Supabase 中创建 `payments` 和 `product_sales` 两张原始表
- 创建一个 SQL View `sales_analysis` 做 LEFT JOIN，匹配不到的标记为"缺失"
- Streamlit 直接查询 View，无需写 JOIN 逻辑

## 数据模型

### 表1: payments（支付数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial | 主键 |
| order_no | text | 订单编号（关联键） |
| payment_time | timestamp | 支付时间 |
| channel | text | 支付渠道（微信/支付宝/云闪付） |
| store_name | text | 入账门店 |
| order_type | text | 订单类型（堂食） |
| total_amount | decimal(10,2) | 交易额 |
| income_amount | decimal(10,2) | 收入金额 |
| merchant_discount | decimal(10,2) | 商家优惠 |
| platform_discount | decimal(10,2) | 平台优惠 |
| refund_amount | decimal(10,2) | 退款金额 |
| service_fee | decimal(10,2) | 服务费 |

### 表2: product_sales（商品明细）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial | 主键 |
| order_no | text | 订单编号（关联键） |
| sale_date | date | 销售日期 |
| product_name | text | 商品名称 |
| unit_price | decimal(10,2) | 商品原价 |
| quantity | int | 销售数量 |
| total_price | decimal(10,2) | 商品销售额 |
| actual_price | decimal(10,2) | 商品实收 |
| discount | decimal(10,2) | 商品优惠 |

### View: sales_analysis

```sql
CREATE VIEW sales_analysis AS
SELECT
  ps.order_no,
  ps.sale_date,
  ps.product_name,
  ps.unit_price,
  ps.quantity,
  ps.total_price,
  ps.actual_price,
  ps.discount,
  p.payment_time,
  p.channel,
  p.store_name,
  p.total_amount AS order_total,
  p.income_amount,
  p.refund_amount,
  p.service_fee,
  CASE WHEN p.order_no IS NULL THEN '缺失' ELSE '已匹配' END AS match_status,
  EXTRACT(HOUR FROM p.payment_time)::int AS hour_of_day
FROM product_sales ps
LEFT JOIN payments p ON ps.order_no = p.order_no;
```

## 分析维度（已确认）

1. **商品销售排行** — 按商品聚合销量、销售额、占比
2. **时间趋势** — 每日/周销售变化折线图
3. **时段分析** — 按小时聚合，分午市/下午茶/晚市
4. **客单价分布** — 不同价位段的单数分布
5. **连带率分析** — 每单商品数分布 + 热门组合排行

## 筛选器

- **时间范围** — 日期选择器（开始/结束）
- **匹配状态** — 下拉选择：全部 / 已匹配 / 缺失
- **商品名称** — 多选下拉，选项来自 View 中 DISTINCT product_name

## Dashboard 布局

### 侧边栏（暗色主题 #1e293b）
- 三个筛选器：时间范围、匹配状态、商品名称
- URL 状态同步（bind="query-params"）

### 主内容区（layout="wide"）

**第1行 — KPI 卡片（4列）**
- 总销售额（¥113,100）
- 总订单数（2,167）
- 平均客单价（¥52.2）
- 连带率（1.29）

**第2行 — 图表（2列）**
- 左侧：商品销售排行 Top 10（ECharts 横向柱状图）
- 右侧：每日销售趋势（ECharts 折线图）

**第3行 — 图表（2列）**
- 左侧：分时销售分布（ECharts 柱状图）
- 右侧：客单价分布（ECharts 饼图/直方图）

**第4行 — 图表（2列）**
- 左侧：每单商品数分布（ECharts 饼图/柱状图）
- 右侧：热销组合 Top 10（ECharts 横向柱状图或表格）

## 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| 数据库 | Supabase (PostgreSQL) | — |
| 前端框架 | Streamlit | latest |
| 图表库 | streamlit-echarts | latest |
| 数据处理 | Pandas | latest |
| 数据导入 | Python (psycopg2 或 supabase-py) | — |

## 实现步骤

1. **Supabase 建表** — 创建 `payments` 和 `product_sales` 两张表
2. **数据导入** — Python 脚本读取 CSV 写入 Supabase
3. **创建 View** — 创建 `sales_analysis` 视图
4. **Streamlit 应用** — 实现完整前端
   - 项目初始化（requirements.txt, .streamlit/config.toml）
   - 数据库连接模块
   - 数据查询函数（带筛选器参数）
   - KPI 卡片
   - ECharts 图表（5个维度）
   - 带率分析（组合计算）
5. **数据预览表格** — 折叠的原始数据预览
