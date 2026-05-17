-- pos_orders 表（收银明细表）
CREATE TABLE IF NOT EXISTS pos_orders (
    id BIGSERIAL PRIMARY KEY,
    order_no TEXT UNIQUE NOT NULL,
    store_name TEXT,
    sale_date DATE NOT NULL,
    total_revenue DECIMAL(10,2) NOT NULL DEFAULT 0,
    gross_income DECIMAL(10,2) NOT NULL DEFAULT 0,
    discount_total DECIMAL(10,2) DEFAULT 0,
    net_revenue DECIMAL(10,2) NOT NULL DEFAULT 0,
    quantity INTEGER DEFAULT 1,
    yunshanfu DECIMAL(10,2) DEFAULT 0,
    wechat_pay DECIMAL(10,2) DEFAULT 0,
    alipay DECIMAL(10,2) DEFAULT 0,
    cash DECIMAL(10,2) DEFAULT 0,
    douyin_coupon DECIMAL(10,2) DEFAULT 0,
    meituan_coupon DECIMAL(10,2) DEFAULT 0,
    free_payment DECIMAL(10,2) DEFAULT 0,
    custom_payment DECIMAL(10,2) DEFAULT 0
);

CREATE INDEX idx_pos_orders_order_no ON pos_orders(order_no);
CREATE INDEX idx_pos_orders_sale_date ON pos_orders(sale_date);

-- product_sales 表（商品明细）
CREATE TABLE IF NOT EXISTS product_sales (
    id BIGSERIAL PRIMARY KEY,
    store_name TEXT,
    sale_date DATE,
    order_no TEXT NOT NULL,
    product_name TEXT,
    unit_price DECIMAL(10,2),
    quantity INTEGER DEFAULT 1,
    total_price DECIMAL(10,2) NOT NULL DEFAULT 0,
    actual_received DECIMAL(10,2) NOT NULL DEFAULT 0,
    discount DECIMAL(10,2) DEFAULT 0
);

CREATE INDEX idx_product_sales_order_no ON product_sales(order_no);
CREATE INDEX idx_product_sales_sale_date ON product_sales(sale_date);
CREATE INDEX idx_product_sales_product_name ON product_sales(product_name);

-- sales_analysis View（LEFT JOIN，收银表匹配商品明细）
CREATE OR REPLACE VIEW sales_analysis AS
SELECT
    ps.order_no,
    ps.sale_date,
    ps.product_name,
    ps.unit_price,
    ps.quantity,
    ps.total_price,
    ps.actual_received,
    ps.discount,
    pos.total_revenue,
    pos.gross_income,
    pos.discount_total,
    pos.net_revenue,
    pos.quantity AS pos_quantity,
    pos.yunshanfu, pos.wechat_pay, pos.alipay, pos.cash,
    pos.douyin_coupon, pos.meituan_coupon, pos.free_payment, pos.custom_payment,
    CASE WHEN pos.order_no IS NULL THEN '缺失' ELSE '已匹配' END AS match_status
FROM product_sales ps
LEFT JOIN pos_orders pos ON ps.order_no = pos.order_no;