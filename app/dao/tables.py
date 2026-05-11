from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class KyAtdcL(Base):
    """출석 테이블 — 날짜 + 이름 조합이 PK."""

    __tablename__ = "KY_ATDC_L"

    atdc_date: Mapped[str] = mapped_column("ATDC_DATE", String(8), primary_key=True)
    atde_name: Mapped[str] = mapped_column("ATDE_NAME", String(100), primary_key=True)


class KyAtdcNotcL(Base):
    """특이사항 테이블 — 날짜가 PK (날짜당 1건)."""

    __tablename__ = "KY_ATDC_NOTC_L"

    atdc_date: Mapped[str] = mapped_column("ATDC_DATE", String(8), primary_key=True)
    atdc_notice: Mapped[str] = mapped_column("ATDC_NOTICE", String(4000), default="")


class KyUserL(Base):
    """사용자 테이블."""

    __tablename__ = "KY_USER_L"

    user_id: Mapped[str] = mapped_column("USER_ID", String(100), primary_key=True)
    user_pw: Mapped[str] = mapped_column("USER_PW", String(200))
