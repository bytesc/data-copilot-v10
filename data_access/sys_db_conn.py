from sqlalchemy import create_engine
from config.get_config import config_data

# Optional engine: the main process always configures ``mysql_sys``, but the LLM
# code sandbox subprocess imports this module (via utils.context_trim ->
# data_access.observe_log) without ever querying the system database. Its rendered
# config therefore omits ``mysql_sys`` on purpose, so no privileged system-database
# engine exists inside the sandbox process. When the key is absent the engine is
# None; every caller that actually uses it runs only in the main process.
_mysql_sys_url = config_data.get('mysql_sys')
sys_engine = (
    create_engine(
        _mysql_sys_url,
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    if _mysql_sys_url
    else None
)
