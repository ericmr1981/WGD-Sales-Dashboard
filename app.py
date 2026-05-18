import streamlit as st
import pandas as pd
from typing import List
from streamlit_echarts import st_echarts
import datetime
import calendar
from db import query_sales_analysis, get_product_names, get_store_names, get_available_months, _get_supabase_config
from queries import (
    compute_product_ranking,
    compute_daily_trend,
    compute_monthly_trend,
    compute_hourly_distribution,
    compute_price_distribution,
    compute_attachment_rate,
    compute_top_combos,
)
from import_utils import parse_pos_orders, parse_revenue_csv, parse_product_sales, check_existing_orders, check_existing_revenue, check_existing_product_sales, upload_batch

st.set_page_config(
    page_title="商品销售分析报表",
    page_icon="📊",
    layout="wide",
)

CHANNEL_META = {
    "wechat_pay": "微信支付",
    "alipay": "支付宝",
    "yunshanfu": "云闪付",
    "cash": "现金",
    "douyin_coupon": "抖音团购券",
    "meituan_coupon": "美团团购券",
    "free_payment": "免支付",
    "custom_payment": "自定义",
}

CHANNEL_KEYS = list(CHANNEL_META.keys())


def get_active_channels() -> List[str]:
    """返回有数据的支付渠道列表（按金额排序）"""
    import json, ssl, urllib.request, urllib.parse

    _url, _key = _get_supabase_config()
    if not _url or not _key:
        return []

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    cols = ",".join(CHANNEL_KEYS)
    url = f"{_url}/rest/v1/order_revenue?select={cols}&limit=5000"
    req = urllib.request.Request(url)
    req.add_header("apikey", _key)
    req.add_header("Authorization", f"Bearer {_key}")
    req.add_header("Accept", "application/json")
    resp = urllib.request.urlopen(req, context=ctx)
    rows = json.loads(resp.read().decode())

    totals = {c: sum(float(r.get(c, 0) or 0) for r in rows) for c in CHANNEL_KEYS}
    return [CHANNEL_META[c] for c, v in sorted(totals.items(), key=lambda x: -x[1]) if v > 0]


product_names = get_product_names()
active_channels = get_active_channels()
store_names = get_store_names()
available_months = get_available_months()

with st.sidebar:
    st.title(":material/filter_alt: 筛选器")

    quick_month = st.selectbox(
        "月份快捷选择",
        ["自定义"] + available_months,
        key="quick_month",
    )
    if quick_month != "自定义":
        year, month = quick_month.split("-")
        month_start = datetime.date(int(year), int(month), 1)
        month_end = datetime.date(int(year), int(month), calendar.monthrange(int(year), int(month))[1])

    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input(
            "开始日期",
            value=month_start if quick_month != "自定义" else pd.to_datetime("2026-04-01"),
        )
    with col2:
        date_to = st.date_input(
            "结束日期",
            value=month_end if quick_month != "自定义" else pd.to_datetime("2026-04-30"),
        )

    selected_products = st.multiselect(
        "商品名称",
        options=product_names,
        default=[],
        key="products",
    )

    selected_channels = st.multiselect(
        "支付方式",
        options=active_channels,
        default=[],
        key="channels",
    )

    selected_stores = st.multiselect(
        "门店",
        options=store_names,
        default=[],
        key="stores",
    )

    # ========== 数据导入 ==========
    st.divider()
    with st.expander(":material/upload: 数据导入", expanded=False):
        import_type = st.radio(
            "文件类型",
            ["收入明细表", "收银明细表", "商品明细表"],
            key="import_type",
            label_visibility="collapsed",
        )
        import_counter = st.session_state.get("import_counter", 0)
        if import_type == "收银明细表":
            accepted = ["xlsx"]
        else:
            accepted = ["csv"]
        uploaded_file = st.file_uploader(
            "选择文件",
            type=accepted,
            key=f"import_file_{import_counter}",
        )

        if uploaded_file and st.session_state.get("import_state") != "parsed":
            if st.button("解析文件"):
                ok = True
                with st.spinner("正在解析..."):
                    try:
                        file_bytes = uploaded_file.getvalue()
                        if import_type == "收入明细表":
                            rows = parse_revenue_csv(file_bytes)
                        elif import_type == "收银明细表":
                            rows = parse_pos_orders(file_bytes)
                        else:
                            rows = parse_product_sales(file_bytes)
                    except Exception as e:
                        st.error(f"解析失败: {e}")
                        ok = False

                    if ok:
                        if not rows:
                            st.warning("文件中没有有效数据")
                            ok = False

                    if ok:
                        with st.spinner("正在检查重复..."):
                            try:
                                if import_type == "收入明细表":
                                    unique_orders = list({r["order_no"] for r in rows})
                                    existing = check_existing_revenue(unique_orders)
                                    new_rows = [r for r in rows if r["order_no"] not in existing]
                                    dup_count = len(rows) - len(new_rows)
                                elif import_type == "收银明细表":
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
                                ok = False

                    if ok and not new_rows:
                        st.info("所有记录均已存在，无需导入")
                        ok = False

                    if ok:
                        st.session_state.import_new_rows = new_rows
                        st.session_state.import_total = len(rows)
                        st.session_state.import_dup = dup_count
                        if import_type == "收入明细表":
                            st.session_state.import_table = "revenue_detail"
                        elif import_type == "收银明细表":
                            st.session_state.import_table = "pos_orders"
                        else:
                            st.session_state.import_table = "product_sales"
                        st.session_state.import_type_parsed = import_type
                        st.session_state.import_state = "parsed"
                        st.rerun()

        # Show preview and confirm after parsing
        if st.session_state.get("import_state") == "parsed":
            new_rows = st.session_state.import_new_rows
            st.caption(f"待导入: {len(new_rows)} 条 | 跳过重复: {st.session_state.import_dup} 条")
            if st.session_state.import_type_parsed == "收入明细表":
                st.dataframe(
                    [{k: r[k] for k in ["order_no", "sale_date", "total_revenue", "payment_split", "payment_method", "member_id"]} for r in new_rows[:5]],
                    height=150,
                )
            elif st.session_state.import_type_parsed == "收银明细表":
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
                        uploaded_count, total_count = upload_batch(st.session_state.import_table, new_rows)
                        st.success(f"成功导入 {uploaded_count}/{total_count} 条记录")
                        for key in ["import_new_rows", "import_total", "import_dup", "import_table",
                                    "import_state", "import_type_parsed"]:
                            if key in st.session_state:
                                del st.session_state[key]
                        st.session_state.import_counter = import_counter + 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"导入失败: {e}")

            if st.button("取消"):
                for key in ["import_new_rows", "import_total", "import_dup", "import_table",
                            "import_state", "import_type_parsed"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.session_state.import_counter = import_counter + 1
                st.rerun()

df_str = date_from.strftime("%Y-%m-%d")
dt_str = date_to.strftime("%Y-%m-%d")

# 将中文渠道名转回字段名
channel_keys = [k for k, v in CHANNEL_META.items() if v in selected_channels]

raw_data = query_sales_analysis(
    date_from=df_str,
    date_to=dt_str,
    match_status="已匹配",
    products=selected_products if selected_products else None,
    payment_channels=channel_keys if channel_keys else None,
    stores=selected_stores if selected_stores else None,
)

if not raw_data:
    st.info("该筛选条件下没有数据")
    st.stop()

data = pd.DataFrame(raw_data)

# 支付方式筛选（订单级别过滤：所选渠道之和 > 0）
if channel_keys:
    order_agg = data.groupby("order_no").first().reset_index()
    # 每行：所选渠道金额之和 > 0
    channel_sum = sum(order_agg[ch].fillna(0) for ch in channel_keys)
    matched_orders = order_agg.loc[channel_sum > 0, "order_no"].tolist()
    data = data[data["order_no"].isin(matched_orders)]
    if data.empty:
        st.info("该筛选条件下没有数据")
        st.stop()

st.title(":material/bar_chart: 商品销售分析报表")

# KPI 计算（按订单去重）
order_level = data.groupby("order_no").first().reset_index()
total_revenue = order_level["total_revenue"].sum()
net_revenue = order_level["net_revenue"].sum()
total_orders = len(order_level)
avg_order = order_level["total_revenue"].mean()
items_per_order = data.groupby("order_no")["quantity"].sum()
attachment_rate = items_per_order.mean()
digital = order_level["wechat_pay"].sum() + order_level["alipay"].sum() + order_level["yunshanfu"].sum()
digital_pct = digital / total_revenue * 100 if total_revenue else 0

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("营业额", f"¥{total_revenue:,.0f}")
with kpi2:
    st.metric("营业净收", f"¥{net_revenue:,.0f}")
with kpi3:
    st.metric("总订单数", f"{total_orders:,}")
with kpi4:
    st.metric("平均客单价", f"¥{avg_order:.1f}")

# Member metrics
has_member = order_level["member_id"].dropna()
has_member = has_member[has_member != ""].astype(str)
has_member = has_member[~has_member.str.startswith("-")]
has_member = has_member[has_member != "--"]
member_orders = order_level.loc[has_member.index]
non_member_orders = order_level.drop(has_member.index)
member_revenue = member_orders["total_revenue"].sum()
member_pct = len(member_orders) / total_orders * 100 if total_orders else 0
member_avg = member_orders["total_revenue"].mean() if len(member_orders) else 0

kpi5, kpi6, kpi7, _ = st.columns(4)
with kpi5:
    st.metric("连带率", f"{attachment_rate:.2f}")
with kpi6:
    st.metric("数字支付占比", f"{digital_pct:.1f}%")
with kpi7:
    st.metric("优惠总额", f"¥{order_level['discount_total'].sum():,.0f}")

kpi8, kpi9, kpi10, _ = st.columns(4)
with kpi8:
    st.metric("会员订单", f"{len(member_orders):,}（{member_pct:.0f}%）")
with kpi9:
    st.metric("会员贡献", f"¥{member_revenue:,.0f}")
with kpi10:
    st.metric("会员客单价", f"¥{member_avg:.1f}")

# ========== 商品排行 + 每日趋势 ==========
col1, col2 = st.columns(2)

with col1:
    st.subheader(":trophy: 商品销售排行 Top 10")
    ranking = compute_product_ranking(data)
    if not ranking.empty:
        names = ranking["product_name"].tolist()
        sales_vals = ranking["total_price"].round(0).astype(int).tolist()
        bar_opts = {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "value"},
            "yAxis": {
                "type": "category",
                "data": names[::-1],
                "axisLabel": {"fontSize": 12},
            },
            "series": [{
                "type": "bar",
                "data": sales_vals[::-1],
                "itemStyle": {
                    "color": {"type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
                              "colorStops": [
                                  {"offset": 0, "color": "#5470c6"},
                                  {"offset": 1, "color": "#91cc75"},
                              ]}
                },
                "label": {"show": True, "position": "right", "formatter": "¥{c}"},
            }],
        }
        st_echarts(options=bar_opts, height="400px", key="ranking", theme="streamlit")

    # Preload all 3 trend dimensions
    trend_daily = compute_daily_trend(data)
    trend_hourly = compute_hourly_distribution(data)
    trend_monthly = compute_monthly_trend(data)

with col2:
    st.subheader(":chart_with_upwards_trend: 销售趋势")

    trend_dim = st.selectbox(
        "时间维度",
        ["每日", "分时", "每月"],
        key="trend_dim",
        label_visibility="collapsed",
    )
    if trend_dim == "分时":
        if not trend_hourly.empty:
            hours = trend_hourly["hour_of_day"].astype(str).tolist()
            h_sales = trend_hourly["total_price"].round(0).astype(int).tolist()
            line_opts = {
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {"type": "category", "data": hours, "name": "小时", "axisLabel": {"fontSize": 11}},
                "yAxis": {"type": "value", "axisLabel": {"formatter": "¥{value}"}},
                "series": [{
                    "type": "bar",
                    "data": h_sales,
                    "itemStyle": {"color": "#5470c6"},
                }],
            }
            st_echarts(options=line_opts, height="400px", key="trend_hourly", theme="streamlit")
        else:
            st.caption("暂无分时数据（需导入含时间的商品明细）")
    elif trend_dim == "每月":
        if not trend_monthly.empty:
            months = trend_monthly["sale_month"].tolist()
            m_sales = trend_monthly["total_price"].round(0).astype(int).tolist()
            line_opts = {
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {"type": "category", "data": months, "axisLabel": {"rotate": 0, "fontSize": 11}},
                "yAxis": {"type": "value", "axisLabel": {"formatter": "¥{value}"}},
                "series": [{
                    "type": "line",
                    "data": m_sales,
                    "smooth": True,
                    "lineStyle": {"width": 3, "color": "#ee6666"},
                    "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                             "colorStops": [
                                                 {"offset": 0, "color": "rgba(238,102,102,0.3)"},
                                                 {"offset": 1, "color": "rgba(238,102,102,0.01)"},
                                             ]}},
                    "itemStyle": {"color": "#ee6666"},
                }],
            }
            st_echarts(options=line_opts, height="400px", key="trend_monthly", theme="streamlit")
        else:
            st.caption("暂无月度数据")
    else:
        if not trend_daily.empty:
            dates = trend_daily["sale_date"].astype(str).tolist()
            daily_sales = trend_daily["total_price"].round(0).astype(int).tolist()
            line_opts = {
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 45, "fontSize": 11}},
                "yAxis": {"type": "value", "axisLabel": {"formatter": "¥{value}"}},
                "series": [{
                    "type": "line",
                    "data": daily_sales,
                    "smooth": True,
                    "lineStyle": {"width": 3, "color": "#5470c6"},
                    "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                             "colorStops": [
                                                 {"offset": 0, "color": "rgba(84,112,198,0.3)"},
                                                 {"offset": 1, "color": "rgba(84,112,198,0.01)"},
                                             ]}},
                    "itemStyle": {"color": "#5470c6"},
                }],
            }
            st_echarts(options=line_opts, height="400px", key="trend_daily", theme="streamlit")

# ========== 支付方式分布 + 时段分布 ==========
col1, col2 = st.columns(2)

with col1:
    st.subheader(":credit_card: 支付方式分布")
    channel_sums = {c: order_level[c].sum() for c in CHANNEL_KEYS}
    active = [(CHANNEL_META[c], v) for c, v in channel_sums.items() if v > 0]
    active.sort(key=lambda x: -x[1])
    if active:
        colors = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272", "#fc8452", "#9a60b4"]
        pie_opts = {
            "tooltip": {"trigger": "item", "formatter": "{b}: ¥{c} ({d}%)"},
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "itemStyle": {"borderRadius": 8, "borderColor": "#fff", "borderWidth": 2},
                "label": {"show": True, "formatter": "{b}: {d}%"},
                "data": [{"name": n, "value": round(v)} for n, v in active],
                "emphasis": {"label": {"show": True, "fontSize": "13", "fontWeight": "bold"}},
            }],
        }
        st_echarts(options=pie_opts, height="350px", key="channel", theme="streamlit")

with col2:
    st.subheader(":moneybag: 客单价分布")
    price_dist = compute_price_distribution(data)
    if price_dist["values"]:
        pie_opts = {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}单 ({d}%)"},
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "itemStyle": {"borderRadius": 8, "borderColor": "#fff", "borderWidth": 2},
                "label": {"show": True, "formatter": "{b}: {d}%"},
                "data": [
                    {"name": l, "value": v}
                    for l, v in zip(price_dist["labels"], price_dist["values"])
                    if v > 0
                ],
                "emphasis": {"label": {"show": True, "fontSize": "14", "fontWeight": "bold"}},
            }],
        }
        st_echarts(options=pie_opts, height="350px", key="price_dist", theme="streamlit")

# ========== 连带率分析 ==========
st.subheader(":link: 连带率分析")
col1, col2 = st.columns(2)

with col1:
    st.caption("每单商品数分布")
    attach = compute_attachment_rate(data)
    if attach["values"]:
        bar_opts = {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "category", "data": attach["labels"]},
            "yAxis": {"type": "value"},
            "series": [{
                "type": "bar",
                "data": attach["values"],
                "itemStyle": {"color": "#91cc75"},
                "label": {"show": True, "position": "top"},
            }],
        }
        st_echarts(options=bar_opts, height="300px", key="attach", theme="streamlit")

with col2:
    st.caption("热销组合 Top 10")
    combos = compute_top_combos(data)
    if combos:
        combo_names = [f"{a} + {b}" for (a, b), _ in combos]
        combo_vals = [c for _, c in combos]
        bar_opts = {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "3%", "right": "15%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "value"},
            "yAxis": {"type": "category", "data": combo_names[::-1], "axisLabel": {"fontSize": 11}},
            "series": [{
                "type": "bar",
                "data": combo_vals[::-1],
                "itemStyle": {"color": "#ee6666"},
                "label": {"show": True, "position": "right", "formatter": "{c}次"},
            }],
        }
        st_echarts(options=bar_opts, height="300px", key="combos", theme="streamlit")

# ========== 数据预览 ==========
with st.expander(":material/table_view: 原始数据预览"):
    preview_cols = ["order_no", "sale_date", "product_name", "total_price",
                    "actual_received", "total_revenue", "net_revenue"]
    available = [c for c in preview_cols if c in data.columns]
    st.dataframe(data[available].head(100), width="stretch")