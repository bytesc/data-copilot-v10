#!/bin/bash
set -e

cd /app

# Read the database URL through the application's config loader so that the
# environment overrides (MYSQL_URL / MYSQL_READONLY_URL / MYSQL_SYS_URL) apply
# here too. Reading config.yaml directly would ignore them and the readiness
# probe could wait on a different database than the one the app actually uses.
echo "Reading database config (config/config.yaml + environment overrides)..."
# Print only host:port/database. The full DSN contains the password and must
# never be echoed (it would leak into `docker compose logs backend`).
DB_TARGET=$(python -c "
from config.get_config import config_data
from sqlalchemy.engine import make_url
url = make_url(config_data['mysql'])
print('{}:{}/{}'.format(url.host, url.port, url.database))
")

echo "Waiting for MySQL to be ready: $DB_TARGET"
until python -c "
import time
import sqlalchemy
from sqlalchemy import text
from config.get_config import config_data
url = config_data['mysql']
while True:
    try:
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        break
    except Exception:
        time.sleep(2)
" 2>/dev/null; do
    sleep 2
done

echo "Starting backend..."

# 确保静态文件目录存在
STATIC_FOLDER=$(python -c "
from config.get_config import config_data
print(config_data.get('static_folder', 'tmp_imgs'))
")
mkdir -p "/app/$STATIC_FOLDER"

cd /app
python main.py
