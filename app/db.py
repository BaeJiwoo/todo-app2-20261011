"""DB 연결. 설정은 환경변수 `DATABASE_URL` 하나뿐이다(12-factor)."""
import os
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def database_url(raw: str) -> str:
    """배포 환경이 주입하는 `postgresql://...?sslmode=require`에 SQLAlchemy용 드라이버 이름을 붙인다.
    그 밖의 주소(예: 시험용 sqlite)는 그대로 쓴다."""
    for prefix in ("postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg2://" + raw[len(prefix):]
    return raw


_url = database_url(os.environ["DATABASE_URL"])
engine = create_engine(_url, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Todo(Base):
    __tablename__ = "todos"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
