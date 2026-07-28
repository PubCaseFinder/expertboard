import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url():
    user = os.environ.get("EXPERTBOARD_MYSQL_USER", "expertboard")
    password = quote_plus(os.environ.get("EXPERTBOARD_MYSQL_PASSWORD", "expertboard_dev"))
    host = os.environ.get("EXPERTBOARD_MYSQL_HOST", "mysql")
    database = os.environ.get("EXPERTBOARD_MYSQL_DATABASE", "expertboard")
    return f"mysql+pymysql://{user}:{password}@{host}:3306/{database}?charset=utf8mb4"


engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
Session = scoped_session(
    sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
)


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
