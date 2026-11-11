# 部署指南

本项目提供三种部署方式：

| 方式 | 组成 | 适用 |
|------|------|------|
| **A. Docker Compose** | MySQL（独立栈）+ 后端 + nginx 前端（可多份） | 推荐，一键起服务；多个前后端可共用一个库 |
| **B. front.py** | Python 轻量反代 + 静态文件 | 无 Docker 的服务器 |
| **C. 手动** | `python main.py` + `npm run dev`/`npm run build` | 开发 |

---

## 部署前先分清 3 个值和 1 条链

一次请求经过：**浏览器 → 前端服务 → 后端 → 数据库**。其中只有 3 个值和"你这台服务器"有关：

| 编号 | 是什么 | 作用 |
|------|--------|------|
| **A** | 后端生成的链接前缀 `static_path` | 后端把图片 / 下载链接写成**绝对地址**时的前缀，必须是**浏览器能打开的地址** |
| **B** | 代理目标 | 前端把 `/api` 等请求转发给后端的地址 |
| **C** | 数据库连接串 | 后端连哪个库 |

**逻辑：A 和 C 永远改 `config/config.yaml`；只有 B 的"位置"随部署方式变。**

- **A（`static_path`）三种部署都改 `config/config.yaml`**（它属于后端，后端只读该文件）。填成"浏览器能访问到前端那个地址"，结尾带 `/`：
  - Docker 前端 8038 → `http://<IP>:8038/`；改完必须 `--build` 重建
  - front.py 前端 8010 → `http://<IP>:8010/`；重启 `python main.py`
  - dev 前端 5173 → 本机用默认即可；跨机填 `http://<IP>:5173/`
- **B（代理目标）**：
  - Docker：写死在 `docker/nginx.conf`（`backend:8008`），**不用改**
  - front.py：`front.py` 顶部常量 `BACKEND_URL`，**一般留空**（自动按 `config.yaml` 的 `server_host`/`server_port` 推导）
  - dev：`vue-front/.env` 的 `DEV_PROXY_TARGET`，默认 `http://127.0.0.1:8008`，**后端不在本机才改**
- **C（数据库）三种部署都改 `config/config.yaml` 的 `mysql*`**，后端就按这里写的地址连库，**库在哪都行**：连本机 docker 库写 `localhost:<宿主发布端口>`（默认 `localhost:3307`；构建时只把主机名 `localhost` 换成 `host.docker.internal`，**端口沿用你写的值**）；连其它机器 / 外部 MySQL 直接写它的真实 `host:port`（非 localhost 不会被改写）。

### 每种部署"最少改什么"

| 部署 | 必改 | 生效方式 |
|------|------|----------|
| **Docker** | `config/config.yaml` 的 `static_path` = `http://<IP>:8038/` | `docker compose -f docker-compose.app.yml -p docker-app up -d --build`（改配置必须重建镜像） |
| **front.py** | `config/config.yaml` 的 `static_path` = `http://<IP>:8010/` | 重启 `python main.py` |
| **dev** | 后端不在本机时改 `vue-front/.env` 的 `DEV_PROXY_TARGET`（同机则不用改） | 重启 `npm run dev`；跨机访问加 `--host` |

> 三者共同点：**只改文件，不碰宿主机环境变量**；前端产物用同源相对地址 `/api`，换服务器**不用重建前端**。

---

## 通用前置条件

1. **LLM API Key**：在 `agent/utils/llm_access/` 放好各模型 `key_file` 指定的密钥文件
   （默认 `api_key_openai.txt`），否则所有 LLM 调用会失败。该目录下的密钥文件**不在仓库中**，
   需自行创建；Docker 部署时必须在 `docker compose -f docker-compose.app.yml -p docker-app build` **之前**就位（否则不会被拷进镜像，
   需 `docker compose -f docker-compose.app.yml -p docker-app up -d --build` 重建）。
2. **业务数据库**：`config/config.yaml` 的 `mysql` 指向业务库（默认 `singapore_land_2`）。
   容器会创建该空库，但**业务数据需要自行导入**。

---

## A. Docker Compose

MySQL 与前后端是**两个互不依赖的独立部署**：不共享网络，前后端 stack 里也不含数据库。

| 编排文件 | 组成 | 说明 |
|------|------|------|
| `docker/docker-compose.mysql.yml` | MySQL | 只把容器 3306 发布到宿主机 3307 |
| `docker/docker-compose.app.yml` | 后端 + nginx 前端 | 可起多份，连哪个库由 `config.yaml` 决定 |

后端连库地址**完全由 `config/config.yaml` 的 DSN 决定**，所以两个 stack 可以任意搭配：
既可以用本仓库 docker 起的库，也可以连其它机器、甚至非 docker 启动的 MySQL。

### 一键启动

```bash
cd docker
# 1) 启动 MySQL（项目名固定 -p docker，沿用既有数据卷 docker_mysql_data）
docker compose -f docker-compose.mysql.yml -p docker up -d

# 2) 启动前后端（连库地址见 config.yaml，两个 stack 互不依赖、顺序可换）
docker compose -f docker-compose.app.yml -p docker-app up -d --build
```

- 前端：<http://localhost:8038/>（nginx，`docker/nginx.conf`，反向代理后端并透传 SSE）
- 后端：<http://localhost:8008/>
- MySQL：宿主机 `3307` → 容器 `3306`

> **后端连库规则**（`config/config.yaml` 的 `mysql` / `mysql_readonly` / `mysql_sys`）：
> - **连本机 docker 起的库**：写 `localhost:<宿主发布端口>`，默认 `localhost:3307`
>   （`docker-compose.mysql.yml` 把库发布在宿主 `3307`）。构建镜像时**只会把主机名
>   `localhost` 自动换成 `host.docker.internal`，端口沿用你写的值**——因此换发布端口只改
>   `config.yaml` 一处，Dockerfile 无需改动。本 stack 已加
>   `extra_hosts: host.docker.internal:host-gateway`，Linux 上也能解析该名字。
> - **连其它库**（外部 MySQL / 其它机器）：直接写它的真实地址，例如
>   `mysql+pymysql://root:123456@192.168.1.5:3306/singapore_land_2`；非 `localhost` 不会被改写。
>
> 前后端 stack **不启动数据库**，请先确保目标 MySQL 已可达（后端入口脚本会自行等待就绪）。
>
> **起第二套前后端**（共用同一个 MySQL，只需错开宿主机端口）：
>
> ```bash
> # PowerShell
> $env:BACKEND_PORT="8018"; $env:FRONTEND_PORT="8048"; docker compose -f docker-compose.app.yml -p docker-app-2 up -d --build
> # bash
> BACKEND_PORT=8018 FRONTEND_PORT=8048 docker compose -f docker-compose.app.yml -p docker-app-2 up -d --build
> ```
>
> 端口默认 `8008`/`8038`，可用 `BACKEND_PORT`/`FRONTEND_PORT` 覆盖（容器内端口不变）。
> 注意每套前后端是独立的前端地址，`config/config.yaml` 的 `static_path` 需指向**本套**的前端端口。

> 前端产物通过**同源相对地址**访问 API（即浏览器当前地址），由 nginx 反向代理到后端。因此前端
> 镜像**不固化后端地址**，不需要为前端配置服务器 IP。但后端生成的 URL（文档下载链接、聊天正文
> 中的图表图片、交互图/CSV 链接、静态地图等）是基于 `static_path` 的**绝对地址**，跨机访问时必须
> 把 `config/config.yaml` 的 `static_path` 设为浏览器可达的前端地址，见下文。

### 数据库初始化

`docker/docker-init.sql` 会在**首次**启动（`mysql_data` 卷为空时）自动执行，创建：

- 业务库 `singapore_land_2`（与 `mysql` / `mysql_readonly` 一致）
- 系统库 `data_copilot_v10_land_sys`（与 `mysql_sys` 一致）+ 全部系统表
- 只读账号 `readonly`（`SELECT`、`SHOW VIEW`）

库名与 `config/config.yaml` 严格对应，**不要**手工改名。若需重新初始化：

```bash
docker compose -f docker-compose.mysql.yml -p docker down -v   # 删除 mysql_data 卷
docker compose -f docker-compose.mysql.yml -p docker up -d
```

> 非容器部署使用仓库根目录的 `init.sql`（只建系统表和 `brief_info` 初始数据、不建库），见下文与 `README.md`。

> MySQL root 口令默认 `123456`，写死在 `docker/docker-compose.mysql.yml`（`MYSQL_ROOT_PASSWORD`）中。
> root 与只读账号 `readonly` 的口令**互相独立**，改哪个只需同步改对应几处：
> - **root 口令**：`docker/docker-compose.mysql.yml` 的 `MYSQL_ROOT_PASSWORD` + `config/config.yaml`
>   的 `mysql`、`mysql_sys` 两条 DSN（`docker-init.sql` 里没有 root 口令）。
> - **`readonly` 口令**：`docker/docker-init.sql` 的 `CREATE USER ... IDENTIFIED BY` +
>   `config/config.yaml` 的 `mysql_readonly` DSN（`docker-compose.mysql.yml` 不受影响）。
> 项目不读取任何环境变量。

### 后端 URL 前缀（config.yaml 的 static_path）

后端生成的**绝对 URL** 由 `config/config.yaml` 的 `static_path` 决定，包括：文档下载链接
（MD/DOCX/PDF）、聊天正文中的图表图片（`/tmp_imgs/*.png`）、`Draw Graph With Data` 交互图、
`Download Data CSV`、静态地图/预测图等。Docker 部署**直接使用镜像内打包的 `config.yaml`**（不再有
环境变量注入），局域网/公网访问时把 `static_path` 改成浏览器可达的**前端**地址，然后重建镜像：

```yaml
# config/config.yaml
static_path: "http://<服务器IP>:8038/"
```

```bash
cd docker
docker compose -f docker-compose.app.yml -p docker-app up -d --build   # 改 config.yaml 后必须重建 backend 镜像才会生效
```

> 说明：nginx 透传 `/tmp_imgs/`（`docker/nginx.conf`），所以 `static_path` 指向前端端口即可让上述
> 所有链接在浏览器侧可用。默认 `http://127.0.0.1:8008/` 仅在本机浏览器有效，跨机访问**必须**修改，
> 否则聊天里的图片和各类下载/交互链接会指向访问者自己的 localhost 而失效。结尾的 `/` 不能省略。
>
> 前端本身无需任何构建期地址配置。

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
python front.py
# 访问 http://localhost:8010/
```

**配置**（直接修改 `front.py` 文件开头的常量，不读取环境变量）：

| 常量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_URL` | `""` | 后端地址；留空则按 `config.yaml` 的 `server_host`/`server_port` 推导 |
| `FRONT_HOST` | `"0.0.0.0"` | 反代监听地址 |
| `FRONT_PORT` | `8010` | 反代监听端口 |
| `PROXY_TIMEOUT` | `600.0` | 反代到后端的超时秒数（含 SSE 流），长任务超过 10 分钟时可调大 |

front.py 同样透传 `/tmp_imgs/`。后端生成的**绝对 URL**（文档下载链接、聊天正文中的图表图片、
交互图/CSV 链接、静态地图等）由 `config/config.yaml` 的 `static_path` 决定，front.py 部署时应设为
`http://<地址>:<FRONT_PORT>/`（例如 `http://<地址>:8010/`），否则这些链接指向 `127.0.0.1:8008`
（浏览器本机），跨机访问时不可用。

---

## C. 手动 / 开发

```bash
pip install -r requirement.txt
python main.py            # 后端 :8008
cd vue-front && npm install && npm run dev   # 前端 :5173，Vite 代理由 .env 的 DEV_PROXY_TARGET 决定
```

---

## 配置项

`config/config.yaml` 的关键字段（完整说明见 [`config_and_models.md`](config_and_models.md)）：

| 字段 | 说明 |
|------|------|
| `server_host` / `server_port` | 后端绑定地址/端口（默认 `0.0.0.0:8008`） |
| `mysql` / `mysql_readonly` / `mysql_sys` | 业务库 / 只读账号 / 系统库 DSN |
| `static_path` | 后端生成的绝对 URL 前缀（文档下载链接、聊天正文中的图表图片、交互图/CSV 链接、静态地图等） |

**单一来源**：上述配置项**只**来自 `config/config.yaml`，程序不读取任何环境变量；如需变更请直接
修改该文件并重启（Docker 部署需 `--build` 重建镜像）。

---

## 端口一览

| 服务 | 容器/进程端口 | 宿主机端口 |
|------|------|------|
| nginx 前端 | 8038 | 8038 |
| 后端 API | 8008 | 8008 |
| MySQL | 3306 | 3307 |
| Vite 开发服务器 | 5173 | 5173 |
| front.py 反代 | 8010（`front.py` 内 `FRONT_PORT`） | 8010 |

---

## 故障排查

| 现象 | 原因 / 处理 |
|------|------|
| 前端页面 404 / 空白 | `vue-front/dist` 未构建。Compose 走多阶段构建不受影响；front.py 需先 `npm run build` |
| SSE 逐字输出卡顿/一次性出现 | 反向代理缓冲未关闭。nginx 需 `proxy_buffering off;`（`docker/nginx.conf` 已配置）；front.py 已设 `X-Accel-Buffering: no` |
| 聊天里的图片 / 下载 / 交互链接点不开（指向 `localhost` 或 `127.0.0.1`） | 后端生成的这些 URL 基于 `config.yaml` 的 `static_path`，默认仅本机可用；设为浏览器可达的前端地址（如 `http://<服务器IP>:8038/`）即可 |
| 上传 CSV/文档报 `413 Request Entity Too Large` | nginx 请求体上限。`docker/nginx.conf` 已设 `client_max_body_size 60m;`；若自定义过该值需 ≥ 后端上限（CSV 50MB / 文档 20MB） |
| 上传文档长时间无响应 / 504 | `/upload-txt/` 会做 LLM 注释生成，耗时可能超过 nginx 默认 60s 读超时；`docker/nginx.conf` 的 `/upload-txt/` 已设 `proxy_read_timeout 600s` |
| SSE / 长任务超过 10 分钟被中断（504 或流式报错） | nginx 各 location 的 `proxy_read_timeout 600s` 与 front.py 默认超时均为 600s 上限；nginx 可调大 `docker/nginx.conf` 中的 `proxy_read_timeout`，front.py 改文件开头的 `PROXY_TIMEOUT`（秒） |
| 后端一直卡在 `Waiting for MySQL to be ready` | 入口脚本按 `config/config.yaml` 的 DSN 解析库地址。确认目标 MySQL 已启动且可达：本机 docker 库需 MySQL stack 在跑（`docker compose -f docker-compose.mysql.yml -p docker up -d`，宿主 3307）；连外部库则确认地址/端口/防火墙。再核对库名与 `docker-init.sql` 一致（`singapore_land_2` / `data_copilot_v10_land_sys`），或 `docker compose -f docker-compose.mysql.yml -p docker down -v` 重初始化 |
| LLM 调用报错/鉴权失败 | 缺少 `agent/utils/llm_access/<key_file>`；放入后重建镜像 |
| 改了 `config.yaml` 后容器行为未变 | 容器用的是构建时打包的 config；改任何配置都需 `docker compose -f docker-compose.app.yml -p docker-app up -d --build` 重建 backend 镜像才会生效 |
| 街景/静态地图截图失败 | 后端镜像中 `playwright install` 有 60s 超时，超时会被跳过（构建日志有 WARNING），此时该功能运行时不可用 |
