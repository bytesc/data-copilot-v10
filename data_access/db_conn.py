from sqlalchemy import create_engine
from config.get_config import config_data

engine = create_engine(
    config_data['mysql'],
    pool_size=20,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

