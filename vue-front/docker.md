# 前端 Docker 方式

前端有两种使用方式：**npm 方式**（见 [`README.md`](README.md)）与 **docker 方式**（本文）。
把前端 + 后端整体部署见 [`../docs/deployment.md`](../docs/deployment.md)。

> 文中端口都只是**默认值，均可修改**。

本目录有两个独立用途的 Dockerfile（`Dockerfile` 仅构建产物、`Dockerfile.dev` 开发模式）；
生产用的前端镜像由 `../docker/Dockerfile.frontend` 多阶段构建（在仓库级 compose 里使用）。

## `Dockerfile` — 仅构建产物

只做 `npm ci` + `npm run build`，不启动服务，用 `docker cp` 或其它镜像复制出 `dist/`：

```bash
docker build -t vue-front-build .
docker create --name vfb vue-front-build
docker cp vfb:/app/dist ./dist
docker rm vfb
```

> 注意：该镜像**不包含** nginx，不能直接对外提供页面。

## `Dockerfile.dev` — 开发镜像

运行 `npm run dev`（Vite HMR），容器内监听 `<前端端口>`（默认 `5173`）：

```bash
docker build -f Dockerfile.dev -t vue-front-dev .

# Docker Desktop（Windows/macOS）：host.docker.internal 自带
docker run -p <前端端口>:<前端端口> \
  -e DEV_PROXY_TARGET=http://host.docker.internal:<后端端口> \
  -v ${PWD}/src:/app/src vue-front-dev

# Linux：需要显式提供 host.docker.internal
docker run -p <前端端口>:<前端端口> --add-host=host.docker.internal:host-gateway \
  -e DEV_PROXY_TARGET=http://host.docker.internal:<后端端口> \
  -v ${PWD}/src:/app/src vue-front-dev
```

> 必须传 `-e DEV_PROXY_TARGET=http://host.docker.internal:<后端端口>`。镜像里烘焙的 `.env` 值是
> `http://127.0.0.1:<后端端口>`，在容器内指向容器自身，`/api`、`/upload-*`、`/tmp_imgs` 都会代理失败。
> `vite.config.js` 会优先读取进程环境变量（见该文件内注释），因此 `-e` 能覆盖 `.env`。
> 后端需在宿主机（或可达地址）另行启动；Windows 下 `${PWD}` 为 PowerShell 写法，cmd 用 `%cd%`。

挂载 `src` 目录可实现热更新；`vite.config.js`、`index.html`、`public/` 等其它文件不在挂载范围内，这些改动需要重建镜像。开发代理目标由 `DEV_PROXY_TARGET` 决定（来自 `.env` 或进程环境变量，非 `VITE_` 前缀，不会注入客户端产物）。

## 生产前端镜像（`../docker/Dockerfile.frontend`）

仓库级部署用的前端镜像由 `../docker/Dockerfile.frontend` **多阶段构建**：先在
`node:20-alpine` 阶段构建 `dist/`，再复制进 `nginx:alpine`，因此**不需要**预先在宿主机构建
`dist/`（`dist/` 已被 gitignore）。容器内 nginx 监听 `<前端端口>`（默认 `8038`），由
`../docker/nginx.conf` 反向代理后端并透传 SSE。它由 `../docker/docker-compose.app.yml` 使用，
启动命令见 [`../docs/deployment.md`](../docs/deployment.md)。

> 前端产物使用**同源相对地址**访问 API，构建时**不固化后端地址**，换服务器部署无需重新构建前端。
> 后端生成的绝对 URL（文档下载链接、聊天正文中的图表图片、交互图/CSV 链接、静态地图等）由
> `config/config.yaml` 的 `static_path` 决定，跨机访问时必须设为浏览器可达的前端地址，详见
> [`../docs/deployment.md`](../docs/deployment.md)。
