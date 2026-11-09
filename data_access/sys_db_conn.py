from sqlalchemy import create_engine
from config.get_config import config_data

sys_engine = create_engine(
    config_data['mysql_sys'],
    pool_size=20,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)
