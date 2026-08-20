#!/bin/bash
set -e

echo "Waiting for MySQL to be ready..."
until python -c "
import time
import sqlalchemy
from sqlalchemy import text
while True:
    try:
        engine = sqlalchemy.create_engine('mysql+pymysql://root:123456@mysql:3306/2026start_v3')
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        break
    except Exception:
        time.sleep(2)
" 2>/dev/null; do
    sleep 2
done

echo "Installing Playwright browsers..."
playwright install chromium || true

echo "Starting backend..."
cd /app
python main.py