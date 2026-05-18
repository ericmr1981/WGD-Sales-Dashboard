from typing import List, Tuple
import pandas as pd
from collections import Counter


def compute_product_ranking(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """商品销售排行"""
    ranking = (
        df.groupby("product_name")
        .agg(
            quantity=("quantity", "sum"),
            total_price=("total_price", "sum"),
            actual_received=("actual_received", "sum"),
        )
        .reset_index()
        .sort_values("total_price", ascending=False)
        .head(top_n)
    )
    ranking["avg_price"] = (ranking["actual_received"] / ranking["quantity"]).round(2)
    ranking["pct"] = (ranking["total_price"] / df["total_price"].sum() * 100).round(1)
    return ranking


def compute_daily_trend(df: pd.DataFrame) -> pd.DataFrame:
    """每日销售趋势"""
    trend = (
        df.groupby("sale_date")
        .agg(
            orders=("order_no", "nunique"),
            total_price=("total_price", "sum"),
        )
        .reset_index()
        .sort_values("sale_date")
    )
    return trend


def compute_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """每月销售趋势"""
    df = df.copy()
    df["sale_month"] = pd.to_datetime(df["sale_date"]).dt.strftime("%Y-%m")
    trend = (
        df.groupby("sale_month")
        .agg(
            orders=("order_no", "nunique"),
            total_price=("total_price", "sum"),
        )
        .reset_index()
        .sort_values("sale_month")
    )
    return trend


def compute_hourly_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """分时销售分布"""
    hourly = df.dropna(subset=["hour_of_day"])
    if hourly.empty:
        return pd.DataFrame()
    dist = (
        hourly.groupby("hour_of_day")
        .agg(
            orders=("order_no", "nunique"),
            total_price=("total_price", "sum"),
        )
        .reset_index()
        .sort_values("hour_of_day")
    )
    return dist


def compute_price_distribution(df: pd.DataFrame) -> dict:
    """客单价分布（按订单）"""
    order_totals = df.groupby("order_no")["total_price"].sum()
    bins = [0, 20, 30, 40, 50, 80, 100, float("inf")]
    labels = ["0-20", "20-30", "30-40", "40-50", "50-80", "80-100", "100+"]
    binned = pd.cut(order_totals, bins=bins, labels=labels, right=True)
    dist = binned.value_counts().sort_index()
    return {"labels": dist.index.tolist(), "values": dist.values.tolist()}


def compute_attachment_rate(df: pd.DataFrame) -> dict:
    """每单商品数分布"""
    items_per = df.groupby("order_no")["quantity"].sum()
    bins = [0, 1, 2, 3, 5, float("inf")]
    labels = ["1件", "2件", "3件", "4-5件", "6件+"]
    binned = pd.cut(items_per, bins=bins, labels=labels, right=True)
    dist = binned.value_counts().sort_index()
    return {"labels": dist.index.tolist(), "values": dist.values.tolist()}


def compute_top_combos(df: pd.DataFrame, top_n: int = 10) -> List[Tuple]:
    """热销商品组合 Top N"""
    order_products = df.groupby("order_no")["product_name"].apply(set)
    pair_counts = Counter()

    for products in order_products:
        products_list = sorted(products)
        if len(products_list) >= 2:
            for i in range(len(products_list)):
                for j in range(i + 1, len(products_list)):
                    pair_counts[(products_list[i], products_list[j])] += 1

    return pair_counts.most_common(top_n)
