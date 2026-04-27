from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nihongo.db")
    engine = create_engine(f"sqlite:///{DB_PATH.replace(os.sep, '/')}", echo=False)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
