from functools import cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core import config


@cache
def engine() -> Engine:
    url = config.database_url().replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


def session() -> Session:
    return Session(engine(), expire_on_commit=False)
