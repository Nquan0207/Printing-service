from __future__ import annotations

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required; copy .env.example to .env")
    return value


def make_engine(url: str | None = None):
    return create_engine(url or database_url(), pool_pre_ping=True)


@contextmanager
def session_scope(engine=None):
    session = sessionmaker(bind=engine or make_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

