# 部署指南

一次请求经过：**浏览器 → 前端服务 → 后端 → 数据库**。

本项目把两件事**拆开独立**，各自都有两种方式，可任意组合：

- **App（前端 + 后端）两种部署方式**：`Docker` / `front.py + main.py`。
- **MySQL 两种部署方式**：`Docker` / `非容器`。

> 前端自身的「构建产物 / 开发服务器 / 前端镜像」不属于部署，见
> [`../vue-front/README.md`](../vue-front/README.md)（npm 方式）与
> [`../vue-front/docker.md`](../vue-front/docker.md)（docker 方式）。
> 本文件只讲把 **App 作为一个整体**怎么部署。

> 文中端口都只是**默认值，均可修改**；一律用 `<前端端口>` / `<后端端口>` / `<宿主发布端口>` 占位，默认数字与修改位置见文末「端口与默认值」。

---

## 0. 一条链和 3 个值

只有 3 个值和「你这台服务器」有关：

| 值 | 是什么 | 放在哪 | 谁读它 |
|----|--------|--------|--------|
| **静态前缀** | `static_path`：后端生成的绝对 URL 前缀（文档下载链接、聊天正文中的图表图片、交互图/CSV 链接、静态地图等），必须是**浏览器能打开的地址**，结尾带 `/` | `config/config.yaml` | 后端 |
| **代理目标** | 前端把 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 转给后端的地址 | **随 App 部署方式变** | 前端 |
| **数据库连接串** | `mysql` / `mysql_readonly` / `mysql_sys` | `config/config.yaml` | 后端 |

**两条规则**：

1. **静态前缀和数据库连接串，两种 App 部署都只改 `config/config.yaml`**（后端只读这个文件，程序不读任何环境变量）。改完的生效方式：Docker 需 `--build` 重建后端镜像；front.py + main.py 重启 `python main.py`。
2. **代理目标的位置随 App 部署方式变**：
   - Docker 方式 → 写死在 `docker/nginx.conf`（`backend:<后端端口>`），默认**不用改**；但如果你改了后端端口，要**同步改这里**。
   - front.py + main.py 方式 → `front.py` 顶部常量 `BACKEND_URL`，**一般留空**（自动按 `config.yaml` 的 `server_host`/`server_port` 推导）。

> 前端产物一律用**同源相对地址** `/api`，不固化后端地址，所以**换服务器不用重建前端**。

**静态前缀（`static_path`）**：填一个**浏览器能访问、且 `/tmp_imgs/...` 能取到文件**的地址即可（前端各方式都反代 `/tmp_imgs/`，后端自己也提供，所以前端、后端地址**都满足**）。**推荐填前端地址**（对外入口、同源、无需额外暴露后端），写法 `http://<IP>:<前端端口>/`，结尾 `/` 不能省。

**数据库连接串只写一处 `config/config.yaml` 的 `mysql*`**，填法见第 2 节：

- 连本机 docker 库 → `localhost:<宿主发布端口>`。构建镜像时只把主机名 `localhost` 换成 `host.docker.internal`，**端口照抄你写的值**。
- 连其它机器 / 外部 MySQL → 写它真实的 `host:port`（非 `localhost` 不会被改写）。

---

## 1. App（前端 + 后端）的两种部署方式

| 部署方式 | 组成 | 代理目标位置 |
|----------|------|--------------|
| **Docker** | nginx 前端容器（`<前端端口>`） + 后端容器（`<后端端口>`） | `docker/nginx.conf` |
| **front.py + main.py** | `python front.py`（前端：静态 + 反代，`<前端端口>`） + `python main.py`（后端，`<后端端口>`） | `front.py` 的 `BACKEND_URL`（默认留空 → 按 `config.yaml` 的 `server_host`/`server_port` 推导） |

### 通用前置条件

1. **LLM API Key**：在 `agent/utils/llm_access/` 放好各模型 `key_file` 指定的密钥文件（默认 `api_key_openai.txt`），否则所有 LLM 调用失败。该目录下的密钥文件**不在仓库中**，需自行创建；Docker 部署必须在 `build` **之前**就位（否则不会被拷进镜像，需 `--build` 重建）。
2. **数据库**：先按第 2 节准备好可用的 MySQL。

### Docker 方式（`docker/docker-compose.app.yml`）

**逻辑**：一个 compose 项目起两个容器。

- 前端由 `docker/Dockerfile.frontend` **多阶段构建**（node 阶段 `npm run build` → 复制进 `nginx:alpine`），所以**不需要**预构建 `vue-front/dist`。容器内 nginx 监听 **`<前端端口>`**，用同源相对地址把 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 反代到 `backend:<后端端口>`，并关闭缓冲透传 SSE。
- 后端由 `docker/Dockerfile.backend` 打包：`COPY . .` 把 `config/config.yaml` **烤进镜像**；构建时 `sed` 只把 DSN 里的主机名 `@localhost:` 换成 `@host.docker.internal:`；入口脚本 `docker-entrypoint.sh` 等数据库就绪后 `python main.py`。
- 前后端 stack **不含数据库、无共享网络**，连哪个库完全由 `config.yaml` 决定。

**改什么**

- `config/config.yaml`
  - `mysql` / `mysql_readonly` / `mysql_sys` → 指向你的库（本机 docker 库写 `localhost:<宿主发布端口>`；外部库写真实 `host:port`）
  - `static_path` → `http://<浏览器可达IP>:<前端端口>/`
- `docker/nginx.conf`：默认不用改。但**改过端口就要同步**——改前端端口改 `listen`；改后端端口改 `set $backend "http://backend:<后端端口>"`。
- `docker/docker-compose.app.yml`：端口映射（前端、后端）。

**命令**（仓库根目录）

```bash
# 首次 / 改了 config.yaml 后（必须 --build，config 是构建时打进镜像的）
docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build

# 只重建后端 / 只重建前端
docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build backend
docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build frontend

# 日志 / 停止
docker compose -f docker/docker-compose.app.yml -p docker-app logs backend
docker compose -f docker/docker-compose.app.yml -p docker-app logs frontend
docker compose -f docker/docker-compose.app.yml -p docker-app down
```



### front.py + main.py 方式

**逻辑**：后端单独跑 `python main.py`（`<后端端口>`）；`front.py` 从 `vue-front/dist/` 提供静态文件，并把 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 反代到后端，SSE 透传（路径含 `/stream/` 的按流式转发，`generate-yaml-outline`、`finalize` 显式列出）。`BACKEND_URL` 留空时按 `config.yaml` 的 `server_host`/`server_port` 推导（`0.0.0.0`/`::`/空 按 `127.0.0.1` 处理）。

**前置：先构建前端产物**（否则页面 404）。构建 / 开发服务器 / 前端镜像的细节见 [`../vue-front/README.md`](../vue-front/README.md) 与 [`../vue-front/docker.md`](../vue-front/docker.md)。

**改什么**

- `config/config.yaml`：`mysql*` 指向你的库；`static_path` → `http://<IP>:<前端端口>/`
- `front.py`（直接改文件开头的常量，不读取环境变量；一般不用改）：

| 常量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_URL` | `""` | 后端地址；留空则按 `config.yaml` 的 `server_host`/`server_port` 推导 |
| `FRONT_HOST` | `"0.0.0.0"` | 反代监听地址 |
| `FRONT_PORT` | `<前端端口>` | 反代监听端口（默认见文末，可改） |
| `PROXY_TIMEOUT` | `600.0` | 反代到后端的超时秒数（含 SSE 流），长任务超过 10 分钟可调大 |

**命令**

```bash
python main.py     # 1) 后端（另一个终端）
python front.py    # 2) 前端反代 → http://localhost:<前端端口>/
```

改 `config.yaml`（`static_path` / `mysql*`）后**重启 `python main.py`** 生效。

---

## 2. MySQL 的两种部署方式

| 部署方式 | 端口 | 初始化脚本 | 会建库？ | 会建只读账号？ |
|----------|------|-----------|----------|----------------|
| **Docker** | 容器默认 `3306` 发布到宿主 `<宿主发布端口>` | `docker/docker-init.sql` | 是 | 是 |
| **非容器** | 数据库监听端口 `<端口>`（默认 `3306`） | 仓库根目录 `init.sql` | 否 | 否 |

### Docker MySQL（`docker/docker-compose.mysql.yml`）

**逻辑**：只跑数据库，固定容器名 `data-copilot-mysql`，把容器端口发布到宿主机 `<宿主发布端口>`（默认避开宿主机本地 MySQL 常用端口）；数据落在 `mysql_data` 卷；**首次启动**（卷为空）自动执行 `docker/docker-init.sql`：建业务库 `singapore_land_2`、系统库 `data_copilot_v10_land_sys` + 全部系统表 + 只读账号 `readonly`。库名/账号要与 `config.yaml` 对应。业务库只建空库，**业务数据需自行导入**。

**改什么**

- `docker/docker-compose.mysql.yml`：`MYSQL_ROOT_PASSWORD`（与 `config.yaml` 的 `mysql` / `mysql_sys` 同步）、端口映射（宿主发布端口可改）
- `docker/docker-init.sql`：`CREATE DATABASE` 库名、`readonly` 密码（与 `config.yaml` 的 `mysql_readonly` 同步）
- root 与 `readonly` 口令**互相独立**：改 root 只同步「compose 的 `MYSQL_ROOT_PASSWORD` + `config.yaml` 的 `mysql`/`mysql_sys`」（`docker-init.sql` 里没有 root 口令）；改 `readonly` 只同步「`docker-init.sql` + `config.yaml` 的 `mysql_readonly`」。

**命令**

```bash
# 启动 / 看日志 / 停止
docker compose -f docker/docker-compose.mysql.yml -p docker up -d
docker compose -f docker/docker-compose.mysql.yml -p docker logs mysql
docker compose -f docker/docker-compose.mysql.yml -p docker down

# 重建空库（删数据卷，慎用）
docker compose -f docker/docker-compose.mysql.yml -p docker down -v
docker compose -f docker/docker-compose.mysql.yml -p docker up -d
```

### 非容器 MySQL

**逻辑**：用宿主机 / 外部已装好的 MySQL。仓库根目录的 `init.sql` **只建系统表 + 4 条 `brief_info` 初始数据**，**不建库、不建只读账号**；必须先建库，再把表建进库里（否则报 `No database selected`）。

**改什么 / 做什么**

- `config/config.yaml`：`mysql` / `mysql_sys` 指向该库（如 `...@<host>:<端口>/...`）；`mysql_readonly` 指向只读账号
- 手工建两个库：业务库 `singapore_land_2`、系统库 `data_copilot_v10_land_sys`（`utf8mb4`）
- 用 `init.sql` 在系统库里建表
- 若要启用只读查询（`exe_sql` 及探索类读取走 `read_only_engine`），**需自建 `readonly` 账号**（`init.sql` 不会建）

**命令**

```bash
# 1) 建库（库名与 config.yaml 一致）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS singapore_land_2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS data_copilot_v10_land_sys DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

# 2) 系统库建表 + 初始化 brief_info
mysql -u root -p data_copilot_v10_land_sys < init.sql

# 3) （启用只读查询时）建只读账号
mysql -u root -p -e "CREATE USER IF NOT EXISTS 'readonly'@'%' IDENTIFIED BY '123456'; GRANT SELECT, SHOW VIEW ON singapore_land_2.* TO 'readonly'@'%'; FLUSH PRIVILEGES;"
```

> `main.py` 启动时也会自动补建缺失的系统表（`CREATE TABLE IF NOT EXISTS`，重复执行安全）；其中 `base_knowledge`、`doc_guide`、`code_guide`、`graph_code_guide`、`think_guide` 仅在 `enable_base_knowledge` 为 true 时创建。

---

## 3. 组合搭配（App 两种 × MySQL 两种 = 4 种）

App 与 MySQL **互相独立**：后端连哪个库**只由 `config.yaml` 的 DSN 决定**。

| App 部署方式 \ MySQL 部署方式 | MySQL = Docker | MySQL = 非容器 / 外部 |
|-------------------------------|----------------|------------------------|
| **Docker** | DSN 写 `localhost:<宿主发布端口>`（`localhost` 会变 `host.docker.internal`，端口照抄）；改完必须 `--build` | DSN 写 `localhost:<端口>` 或真实 `host:port`（非 `localhost` 不改写）；后端容器靠 `extra_hosts` 访问宿主 |
| **front.py + main.py** | DSN 按你的库写 `host:port` | 同上；front.py 不碰库，只反代 |

**记忆要点**

- 换 App 部署方式 → 只有**代理目标**的位置变（`nginx.conf` / `front.py`）；静态前缀和数据库连接串永远在 `config.yaml`。
- 换 MySQL 部署方式 → 只有**数据库连接串的 `host:port`** 变；Docker 场景依赖「只换主机名、端口照抄」这条规则。
- 每套 App 的 `static_path` 要指向**本套前端端口**。

---

## 4. 配置项汇总

`config/config.yaml` 的关键字段（完整说明见 [`config_and_models.md`](config_and_models.md)）：

| 字段 | 说明 |
|------|------|
| `server_host` / `server_port` | 后端绑定地址/端口 |
| `mysql` / `mysql_readonly` / `mysql_sys` | 业务库 / 只读账号 / 系统库 DSN |
| `static_path` | 后端生成的绝对 URL 前缀（文档下载链接、聊天正文中的图表图片、交互图/CSV 链接、静态地图等） |

**单一来源**：上述配置项**只**来自 `config/config.yaml`，程序不读取任何环境变量；如需变更请直接修改该文件并重启（Docker 部署需 `--build` 重建后端镜像）。

---

## 5. 端口与默认值（均可修改）

| 端口 | 默认 | 改哪里 |
|------|------|--------|
| 后端端口 | `8008` | `config/config.yaml` 的 `server_port`（前端代理目标随之；Docker 还要同步 `docker/nginx.conf` 的 `$backend`） |
| 前端端口（Docker） | `8038` | `docker/nginx.conf` 的 `listen` + `docker/docker-compose.app.yml` 的端口映射 |
| 前端端口（front.py） | `8010` | `front.py` 的 `FRONT_PORT` |
| MySQL 容器端口 | `3306` | `docker/docker-compose.mysql.yml` 的端口映射（容器内一般保持 `3306`） |
| MySQL 宿主发布端口 | `3307` | `docker/docker-compose.mysql.yml` 的端口映射（同时把 `config.yaml` 的 DSN 端口改成一致） |

---

## 6. 故障排查

| 现象 | 原因 / 处理 |
|------|------|
| 前端页面 404 / 空白 | `vue-front/dist` 未构建。Docker 方式走多阶段构建不受影响；front.py + main.py 方式需先构建前端产物（见 [`../vue-front/README.md`](../vue-front/README.md)） |
| SSE 逐字输出卡顿/一次性出现 | 反向代理缓冲未关闭。Docker 需 `proxy_buffering off;`（`docker/nginx.conf` 已配置）；front.py 已设 `X-Accel-Buffering: no` |
| 聊天里的图片 / 下载 / 交互链接点不开（指向 `localhost` 或 `127.0.0.1`） | 后端生成的这些 URL 基于 `config.yaml` 的 `static_path`，默认仅本机可用；设为浏览器可达的前端地址（如 `http://<服务器IP>:<前端端口>/`）即可 |
| 上传 CSV/文档报 `413 Request Entity Too Large` | nginx 请求体上限。`docker/nginx.conf` 已设 `client_max_body_size 60m;`；若自定义过该值需 ≥ 后端上限（CSV 50MB / 文档 20MB） |
| 上传文档长时间无响应 / 504 | `/upload-txt/` 会做 LLM 注释生成，耗时可能超过 nginx 默认 60s 读超时；`docker/nginx.conf` 的 `/upload-txt/` 已设 `proxy_read_timeout 600s` |
| SSE / 长任务超过 10 分钟被中断（504 或流式报错） | nginx 各 location 的 `proxy_read_timeout 600s` 与 front.py 默认超时均为 600s 上限；nginx 可调大 `docker/nginx.conf` 中的 `proxy_read_timeout`，front.py 改文件开头的 `PROXY_TIMEOUT`（秒） |
| 后端一直卡在 `Waiting for MySQL to be ready` | 入口脚本按 `config/config.yaml` 的 DSN 解析库地址。确认目标 MySQL 已启动且可达：本机 docker 库需 MySQL stack 在跑（`docker compose -f docker/docker-compose.mysql.yml -p docker up -d`），且 `config.yaml` 的 DSN 端口写成宿主发布端口；连外部库则确认地址/端口/防火墙。再核对库名与 `docker-init.sql` 一致（`singapore_land_2` / `data_copilot_v10_land_sys`），或 `docker compose -f docker/docker-compose.mysql.yml -p docker down -v` 重初始化 |
| LLM 调用报错/鉴权失败 | 缺少 `agent/utils/llm_access/<key_file>`；放入后重建镜像（Docker）或重启后端 |
| 改了 `config.yaml` 后容器行为未变 | 容器用的是构建时打包的 config；改任何配置都需 `docker compose -f docker/docker-compose.app.yml -p docker-app up -d --build` 重建后端镜像才会生效 |
| 街景/静态地图截图失败 | 后端镜像中 `playwright install` 有 60s 超时，超时会被跳过（构建日志有 WARNING），此时该功能运行时不可用 |
