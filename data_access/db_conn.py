from sqlalchemy import create_engine
from config.get_config import config_data

# Optional engine: the privileged user-database engine is only used by features
# that modify the database (upload / edit / comment), which all run in the main
# process. The sandbox subprocess imports this module only to reach its tool
# functions and never uses the privileged engine, so its minimal config omits
# ``mysql`` altogether and no privileged engine is created inside the sandbox.
_mysql_url = config_data.get('mysql')
engine = (
    create_engine(
        _mysql_url,
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    if _mysql_url
    else None
)
