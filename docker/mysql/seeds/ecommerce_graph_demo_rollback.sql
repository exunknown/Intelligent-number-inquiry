SET NAMES utf8mb4;

USE dw;

-- 先删除订单，再删除本批演示数据使用的客户和商品维度。
DELETE FROM fact_order
WHERE order_id LIKE 'DEMO2025%';

DELETE FROM dim_customer
WHERE customer_id IN ('C901', 'C902', 'C903', 'C904', 'C905');

DELETE FROM dim_product
WHERE product_id IN ('P901', 'P902', 'P903', 'P904', 'P905');
