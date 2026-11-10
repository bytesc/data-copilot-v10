# 部署指南

本项目提供三种部署方式：

| 方式 | 组成 | 适用 |
|------|------|------|
| **A. Docker Compose** | MySQL + 后端 + nginx 前端 | 推荐，一键起服务 |
| **B. front.py** | Python 轻量反代 + 静态文件 | 无 Docker 的服务器 |
| **C. 手动** | `python main.py` + `npm run dev`/`npm run build` | 开发 |

---

## 通用前置条件

1. **LLM API Key**：在 `agent/utils/llm_access/` 放好各模型 `key_file` 指定的密钥文件
   （默认 `api_key_openai.txt`），否则所有 LLM 调用会失败。该目录下的密钥文件**不在仓库中**，
   需自行创建；Docker 部署时必须在 `docker compose build` **之前**就位（否则不会被拷进镜像，
   需 `docker compose up -d --build` 重建）。
2. **业务数据库**：`config/config.yaml` 的 `mysql` 指向业务库（默认 `singapore_land_2`）。
   容器会创建该空库，但**业务数据需要自行导入**。

---

## A. Docker Compose

编排文件：`docker/docker-compose.yml`。

### 一键启动

```bash
cd docker
docker compose build
docker compose up -d
```

- 前端：<http://localhost:8038/>（nginx，`docker/nginx.conf`，反向代理后端并透传 SSE）
- 后端：<http://localhost:8008/>
- MySQL：宿主机 `3307` → 容器 `3306`（容器内后端始终连 `mysql:3306`）

### 数据库初始化

`docker/docker-init.sql` 会在**首次**启动（`mysql_data` 卷为空时）自动执行，创建：

- 业务库 `singapore_land_2`（与 `mysql` / `mysql_readonly` 一致）
- 系统库 `data_copilot_v10_land_sys`（与 `mysql_sys` 一致）+ 全部系统表
- 只读账号 `readonly`（`SELECT`、`SHOW VIEW`）

库名与 `config/config.yaml` 严格对应，**不要**手工改名。若需重新初始化：

```bash
docker compose down -v   # 删除 mysql_data 卷
docker compose up -d
```

> 非容器部署使用仓库根目录的 `init.sql`（只建系统表、不建库），见下文与 `README.md`。

### 下载链接前缀

后端生成的文档/图片下载链接由 `static_path` 决定。Compose 通过 `STATIC_PATH` 环境变量注入
（默认 `http://localhost:8038/`）。局域网/公网访问时改成浏览器可访问的地址：

```bash
# Windows PowerShell
$env:STATIC_PATH="http://<服务器IP>:8038/"
# Linux/macOS
STATIC_PATH=http://<服务器IP>:8038/ docker compose up -d
```

### 前端构建

前端镜像由 `docker/Dockerfile.frontend` **多阶段构建**（`node` 阶段 `npm run build` → `nginx`
阶段），因此**不需要**预先构建 `vue-front/dist`。

---

## B. front.py（轻量反代）

用 Python 提供前端静态文件 + API 反向代理 + SSE 透传，替代 nginx。

```bash
# 1) 构建前端产物（必须，否则页面 404）
cd vue-front && npm install && npm run build && cd ..

# 2) 启动后端（另开一个终端）
python main.py

# 3) 启动前端反代
FRONT_PORT=8010 python front.py
# 访问 http://localhost:8010/
```

**环境变量**：

| 变量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_URL` | 由 `config.yaml` 的 `server_host`/`server_port` 推导 | 后端地址 |
| `FRONT_HOST` | `0.0.0.0` | 反代监听地址 |
| `FRONT_PORT` | `8010` | 反代监听端口 |

下载链接前缀同样由 `static_path` / `STATIC_PATH` 决定，front.py 部署时应设为
`http://<地址>:<FRONT_PORT>/`。

---

## C. 手动 / 开发

```bash
pip install -r requirement.txt
python main.py            # 后端 :8008
cd vue-front && npm install && npm run dev   # 前端 :5173，Vite 代理由 .env 的 VITE_SERVER_URL 决定
```

---

## 配置项

`config/config.yaml` 的关键字段（完整说明见 [`config_and_models.md`](config_and_models.md)）：

| 字段 | 说明 |
|------|------|
| `server_host` / `server_port` | 后端绑定地址/端口（默认 `0.0.0.0:8008`） |
| `mysql` / `mysql_readonly` / `mysql_sys` | 业务库 / 只读账号 / 系统库 DSN |
| `static_path` | 下载链接前缀 |

**环境变量覆盖**（存在时优先于 config.yaml，便于容器化）：`STATIC_PATH`、`SERVER_HOST`、
`SERVER_PORT`、`MYSQL_URL`、`MYSQL_READONLY_URL`、`MYSQL_SYS_URL`。

---

## 端口一览

| 服务 | 容器/进程端口 | 宿主机端口 |
|------|------|------|
| nginx 前端 | 8038 | 8038 |
| 后端 API | 8008 | 8008 |
| MySQL | 3306 | 3307 |
| Vite 开发服务器 | 5173 | 5173 |

---

## 故障排查

| 现象 | 原因 / 处理 |
|------|------|
| 后端卡在 `Waiting for MySQL to be ready` | `config.yaml` 的库名与 `docker-init.sql` 不一致；改回 `singapore_land_2` / `data_copilot_v10_land_sys`，或 `docker compose down -v` 重初始化 |
| 前端页面 404 / 空白 | `vue-front/dist` 未构建。Compose 走多阶段构建不受影响；front.py 需先 `npm run build` |
| SSE 逐字输出卡顿/一次性出现 | 反向代理缓冲未关闭。nginx 需 `proxy_buffering off;`（`docker/nginx.conf` 已配置）；front.py 已设 `X-Accel-Buffering: no` |
| 下载链接指向 `127.0.0.1` / 点不开 | 设置 `static_path` 或 `STATIC_PATH` 为浏览器可达地址 |
| LLM 调用报错/鉴权失败 | 缺少 `agent/utils/llm_access/<key_file>`；放入后重建镜像 |
| 改了 `config.yaml` 后容器行为未变 | 容器用的是构建时打包的 config；改库地址等请用环境变量，或重建镜像 |
