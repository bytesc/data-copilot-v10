# 部署指南

App（前端 + 后端）与 MySQL 分开部署、互不依赖：App 两种方式，MySQL 两种方式。

**前置**：模型密钥放到 `agent/utils/llm_access/<key_file>`（默认 `api_key_openai.txt`）；Docker 部署需在 `build` 前就位。

---

## App 部署

### Docker（`docker/docker-compose.app.yml`）

nginx 前端容器 + 后端容器；前端多阶段构建，无需预构建 `vue-front/dist`。

改 `config/config.yaml`：

```yaml
static_path: "http://<IP>:<前端端口>/"
mysql: "mysql+pymysql://root:<密码>@<host>:<端口>/singapore_land_2"
mysql_readonly: "mysql+pymysql://readonly:<密码>@<host>:<端口>/singapore_land_2"
mysql_sys: "mysql+pymysql://root:<密码>@<host>:<端口>/data_copilot_v10_land_sys"
```

连本机 docker 库：`<host>:<端口>` 写 `localhost:<宿主发布端口>`（构建时 `localhost` 换成 `host.docker.internal`，端口照抄）；连外部库写真实地址。

```bash
docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build          # 首次 / 改 config.yaml 后
docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build backend   # 只重建后端
docker compose -f docker/docker-compose.app.yml -p docker-app logs backend
docker compose -f docker/docker-compose.app.yml -p docker-app down
```

**不改端口（默认）** —— `docker/docker-compose.app.yml`、`docker/nginx.conf` 用现有默认值，不用改：

```yaml
# docker/docker-compose.app.yml
services:
  backend:
    ports: ["8008:8008"]
  frontend:
    ports: ["8038:8038"]
```

```nginx
# docker/nginx.conf
listen 8038;
set $backend "http://backend:8008";
```

**改端口** —— 同步改这两个文件：

```yaml
# docker/docker-compose.app.yml
services:
  backend:
    ports: ["<后端端口>:<后端端口>"]
  frontend:
    ports: ["<前端端口>:<前端端口>"]
```

```nginx
# docker/nginx.conf
listen <前端端口>;
set $backend "http://backend:<后端端口>";
```

> 前端只改宿主发布端口（映射左侧，容器内仍为默认端口）时，`nginx.conf` 的 `listen` 不用动。

前端 `http://localhost:<前端端口>/`，后端 `http://localhost:<后端端口>/`。

### front.py + main.py

`python main.py`（后端）+ `python front.py`（前端静态 + 反向代理）。前置：先构建前端产物（见 [`vue-front/README.md`](../vue-front/README.md)）。

改 `config/config.yaml`：`static_path`、`mysql` / `mysql_readonly` / `mysql_sys`（同上）。

```bash
python main.py      # 后端（另一个终端）
python front.py     # 前端 → http://localhost:<前端端口>/
```

**不改端口（默认）** —— `front.py` 顶部常量用默认值，不用改：

```python
# front.py
BACKEND_URL = ""        # 留空 → 按 config.yaml 的 server_host / server_port 推导
FRONT_PORT = 8010
```

**改端口** —— 改 `front.py` 的 `FRONT_PORT`：

```python
# front.py
FRONT_PORT = <前端端口>
```

> 这里指前端端口；后端端口只需改 `config.yaml` 的 `server_port`，`BACKEND_URL` 留空会自动跟随。

改 `config.yaml` 后重启 `python main.py`。

---

## MySQL 部署

### Docker（`docker/docker-compose.mysql.yml`）

首次启动执行 `docker/docker-init.sql`：建业务库 `singapore_land_2`、系统库 `data_copilot_v10_land_sys`（含系统表）、只读账号 `readonly`。

改：

```yaml
# docker/docker-compose.mysql.yml
MYSQL_ROOT_PASSWORD: "<密码>"      # 与 config.yaml 的 mysql / mysql_sys 一致
ports:
  - "<宿主发布端口>:3306"
```

```sql
-- docker/docker-init.sql
CREATE DATABASE IF NOT EXISTS singapore_land_2 ...                 -- 库名，与 config.yaml 一致
CREATE USER IF NOT EXISTS 'readonly'@'%' IDENTIFIED BY '<密码>';  -- 与 config.yaml 的 mysql_readonly 一致
```

```bash
docker compose -f docker/docker-compose.mysql.yml -p docker up -d
docker compose -f docker/docker-compose.mysql.yml -p docker logs mysql
docker compose -f docker/docker-compose.mysql.yml -p docker down        # 停止
docker compose -f docker/docker-compose.mysql.yml -p docker down -v     # 删数据卷、重建空库（慎用）
```

### 非容器

已装好的 MySQL + 仓库根目录 `init.sql`（只建系统表 + `brief_info`，不建库、不建只读账号）。

改 `config/config.yaml` 的 `mysql` / `mysql_readonly` / `mysql_sys` 指向该库。

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS singapore_land_2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS data_copilot_v10_land_sys DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
mysql -u root -p data_copilot_v10_land_sys < init.sql
mysql -u root -p -e "CREATE USER IF NOT EXISTS 'readonly'@'%' IDENTIFIED BY '123456'; GRANT SELECT, SHOW VIEW ON singapore_land_2.* TO 'readonly'@'%'; FLUSH PRIVILEGES;"
```

> `readonly` 用于只读查询（`exe_sql` 及探索类读取），`init.sql` 不建，需自行执行；`main.py` 启动时也会自动补建缺失的系统表。

---

## 端口与默认值（均可修改）

| 端口 | 默认 | 改哪里 |
|------|------|--------|
| 后端 | `8008` | `config/config.yaml` 的 `server_port`（Docker 还要同步 `docker/nginx.conf` 的 `$backend`、`docker-compose.app.yml` 的 `ports` 与 `healthcheck`） |
| 前端（Docker） | `8038` | `docker/docker-compose.app.yml` 的 `ports`、`docker/nginx.conf` 的 `listen` |
| 前端（front.py） | `8010` | `front.py` 的 `FRONT_PORT` |
| MySQL 容器 | `3306` | `docker/docker-compose.mysql.yml` 的 `ports` |
| MySQL 宿主发布 | `3307` | `docker/docker-compose.mysql.yml` 的 `ports`（同步 `config.yaml` 的 DSN 端口） |

---

## 故障排查

| 现象 | 原因 / 处理 |
|------|------|
| 前端页面 404 / 空白 | `vue-front/dist` 未构建。Docker 走多阶段构建不受影响；front.py + main.py 需先构建前端产物（见 [`vue-front/README.md`](../vue-front/README.md)） |
| SSE 逐字输出卡顿/一次性出现 | 反向代理缓冲未关闭。Docker 需 `proxy_buffering off;`（`docker/nginx.conf` 已配置）；front.py 已设 `X-Accel-Buffering: no` |
| 聊天里的图片 / 下载 / 交互链接点不开（指向 `localhost` / `127.0.0.1`） | 这些 URL 基于 `config.yaml` 的 `static_path`；设为浏览器可达的前端地址（如 `http://<服务器IP>:<前端端口>/`） |
| 上传报 `413 Request Entity Too Large` | nginx 请求体上限，`docker/nginx.conf` 已设 `client_max_body_size 60m;`（≥ 后端上限 CSV 50MB / 文档 20MB） |
| 上传文档无响应 / 504 | `/upload-txt/` 做 LLM 注释生成，`docker/nginx.conf` 的 `/upload-txt/` 已设 `proxy_read_timeout 600s` |
| SSE / 长任务超过 10 分钟被中断 | `proxy_read_timeout` / `PROXY_TIMEOUT` 默认 600s；分别改 `docker/nginx.conf`、`front.py` 文件开头的 `PROXY_TIMEOUT` |
| 后端一直卡在 `Waiting for MySQL to be ready` | 确认 MySQL 可达且 `config.yaml` 的 DSN 端口写对（本机 docker 库写宿主发布端口）；库名与 `docker-init.sql` 一致；必要时 `docker compose -f docker/docker-compose.mysql.yml -p docker down -v` 重初始化 |
| LLM 调用鉴权失败 | 缺少 `agent/utils/llm_access/<key_file>`；补上后重建镜像（Docker）或重启后端 |
| 改了 `config.yaml` 后容器行为未变 | 容器用的是构建时打包的 config，需 `docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build` 重建后端镜像 |
| 街景/静态地图截图失败 | 后端镜像 `playwright install` 有 60s 超时，超时被跳过（构建日志有 WARNING），该功能运行时不可用 |
