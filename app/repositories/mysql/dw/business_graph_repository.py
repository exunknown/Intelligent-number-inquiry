"""电商业务知识图谱构建所需的数仓聚合原始行。"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CustomerGraphRow:
    """业务图谱需要的客户最小字段集合。"""

    customer_id: str
    member_level: str


@dataclass(frozen=True)
class OrderGraphRow:
    """业务图谱需要的订单宽行。"""

    order_id: str
    customer_id: str
    product_id: str
    product_name: str
    category: str
    brand: str
    region_id: str
    region_name: str
    order_quantity: int
    order_amount: Decimal
    date_id: int


class BusinessGraphSourceRepository:
    """从 DW 读取构建业务图谱的最小脱敏数据集。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_customer_rows(self) -> list[CustomerGraphRow]:
        result = await self.session.execute(
            text(
                """
                SELECT customer_id, member_level
                FROM dim_customer
                WHERE customer_id IS NOT NULL
                ORDER BY customer_id
                """
            )
        )
        return [
            CustomerGraphRow(
                customer_id=str(row["customer_id"]),
                member_level=str(row["member_level"] or "未分层"),
            )
            for row in result.mappings().all()
        ]

    async def load_order_rows(self) -> list[OrderGraphRow]:
        result = await self.session.execute(
            text(
                """
                SELECT
                    o.order_id,
                    o.customer_id,
                    o.product_id,
                    p.product_name,
                    p.category,
                    p.brand,
                    o.region_id,
                    r.region_name,
                    o.order_quantity,
                    o.order_amount,
                    o.date_id
                FROM fact_order AS o
                INNER JOIN dim_product AS p ON p.product_id = o.product_id
                INNER JOIN dim_region AS r ON r.region_id = o.region_id
                WHERE o.order_id IS NOT NULL
                  AND o.customer_id IS NOT NULL
                  AND o.product_id IS NOT NULL
                ORDER BY o.order_id, o.product_id
                """
            )
        )
        return [
            OrderGraphRow(
                order_id=str(row["order_id"]),
                customer_id=str(row["customer_id"]),
                product_id=str(row["product_id"]),
                product_name=str(row["product_name"] or row["product_id"]),
                category=str(row["category"] or "未分类"),
                brand=str(row["brand"] or "未知品牌"),
                region_id=str(row["region_id"]),
                region_name=str(row["region_name"] or row["region_id"]),
                order_quantity=int(row["order_quantity"] or 0),
                order_amount=Decimal(str(row["order_amount"] or 0)),
                date_id=int(row["date_id"]),
            )
            for row in result.mappings().all()
        ]
