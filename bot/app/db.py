from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import SETTINGS

engine = create_engine(SETTINGS.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
