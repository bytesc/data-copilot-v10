#!/bin/bash
set -e

echo "Reading database config from config/config.yaml..."
DB_URL=$(python -c "
import yaml
with open('/app/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
print(cfg['mysql'])
")

echo "Waiting for MySQL to be ready: $DB_URL"
until python -c "
import time
import sqlalchemy
from sqlalchemy import text
url = '$DB_URL'
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
import yaml
with open('/app/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('static_folder', 'tmp_imgs'))
")
mkdir -p "/app/$STATIC_FOLDER"

cd /app
python main.py