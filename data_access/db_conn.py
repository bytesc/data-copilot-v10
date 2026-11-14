from sqlalchemy import create_engine, event
from config.get_config import config_data


def query_timeout_seconds():
    """Configured per-query SQL timeout in seconds (``0`` / absent = no limit).

    Read from ``sql_query_timeout`` in config.yaml. It is applied as the
    server-side ``max_execution_time`` cap (SELECT-only) so a runaway query
    (e.g. an accidental cross join) is aborted by the server while the
    connection stays usable.
    """
    try:
        seconds = float(config_data.get("sql_query_timeout", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return seconds if seconds > 0 else 0.0


# Default socket read/write timeout (seconds) when ``sql_socket_timeout`` is
# absent. Kept deliberately generous: this is a safety net against a truly stuck
# connection, NOT the per-query cap. A small value here would abort legitimate
# long-running queries or large result transfers mid-stream.
DEFAULT_SOCKET_TIMEOUT = 300.0


def socket_timeout_seconds():
    """pymysql socket read/write timeout in seconds (``0`` = disabled).

    Read from ``sql_socket_timeout`` in config.yaml; when the key is absent the
    generous ``DEFAULT_SOCKET_TIMEOUT`` is used, and a value ``<= 0`` disables
    the socket timeout entirely. It is intentionally independent of
    ``sql_query_timeout`` so the per-statement cap (``max_execution_time``) does
    not also impose a tight socket deadline on large result sets.
    """
    raw = config_data.get("sql_socket_timeout", DEFAULT_SOCKET_TIMEOUT)
    if raw is None:
        raw = DEFAULT_SOCKET_TIMEOUT
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_SOCKET_TIMEOUT
    return seconds if seconds > 0 else 0.0


def build_connect_args(seconds):
    """pymysql socket read/write timeout for ``create_engine(connect_args=...)``.

    Must be passed at engine creation (SQLAlchemy applies ``connect_args`` only
    then). Applies to every statement and every server version, so it is the
    guaranteed layer; returns ``{}`` when the socket timeout is disabled.
    """
    if not seconds:
        return {}
    return {"read_timeout": seconds, "write_timeout": seconds}


def register_query_timeout(engine, seconds):
    """Best-effort per-session ``max_execution_time`` cap on new connections.

    Adds a server-side execution cap (milliseconds) for read-only SELECTs on
    top of the socket timeout. Servers that do not support the variable (older
    MySQL, MariaDB) raise and are silently ignored, leaving the socket timeout
    in effect. Register right after ``create_engine`` so pooled connections
    created later inherit it; an unsupported server never blocks a connection.
    """
    if engine is None or not seconds:
        return engine
    milliseconds = int(seconds * 1000)

    @event.listens_for(engine, "connect")
    def _set_max_execution_time(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SET SESSION max_execution_time = %s", (milliseconds,))
            finally:
                cursor.close()
        except Exception:
            # Unsupported by this server: the socket read/write timeout still
            # applies, so a connection must never fail because of this call.
            pass

    return engine


def _create_business_engine(url, query_seconds, socket_seconds):
    if not url:
        return None
    engine = create_engine(
        url,
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args=build_connect_args(socket_seconds),
    )
    return register_query_timeout(engine, query_seconds)


# Optional engine: the privileged user-database engine is only used by features
# that modify the database (upload / edit / comment), which all run in the main
# process. The sandbox subprocess imports this module only to reach its tool
# functions and never uses the privileged engine, so its minimal config omits
# ``mysql`` altogether and no privileged engine is created inside the sandbox.
_MYSQL_QUERY_TIMEOUT = query_timeout_seconds()
_MYSQL_SOCKET_TIMEOUT = socket_timeout_seconds()
engine = _create_business_engine(
    config_data.get('mysql'), _MYSQL_QUERY_TIMEOUT, _MYSQL_SOCKET_TIMEOUT
)
