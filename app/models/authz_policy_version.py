"""授权策略版本 ORM 模型。"""

from sqlalchemy import BigInteger, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuthzPolicyVersionMySQL(Base):
    __tablename__ = "authz_policy_version"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
