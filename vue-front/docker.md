# 前端 Docker 说明

本目录有两个独立用途的 Dockerfile；仓库级部署（含后端 + MySQL + nginx 前端）请见
[`../docs/deployment.md`](../docs/deployment.md) 的 Docker Compose 部分。

## `Dockerfile` — 仅构建产物

只做 `npm ci` + `npm run build`，不启动服务，用 `docker cp` 或其它镜像复制出 `dist/`：

```bash
docker build -t vue-front-build .
docker create --name vfb vue-front-build
docker cp vfb:/app/dist ./dist
docker rm vfb
```

> 注意：该镜像**不包含** nginx，不能直接对外提供页面。

## `Dockerfile.dev` — 开发模式

运行 `npm run dev`（Vite HMR），暴露 5173 端口：

```bash
docker build -f Dockerfile.dev -t vue-front-dev .
docker run -p 5173:5173 -v ${PWD}/src:/app/src vue-front-dev
```

挂载 `src` 目录可实现热更新。开发代理目标由 `.env` 的 `VITE_SERVER_URL` 决定。

## 生产部署（Docker Compose）

实际生产用的前端镜像由 `../docker/Dockerfile.frontend` **多阶段构建**：先在
`node:20-alpine` 阶段构建 `dist/`，再复制进 `nginx:alpine`，因此**不需要**预先在宿主机构建
`dist/`（`dist/` 已被 gitignore）。前端容器监听 `8038`，由 `../docker/nginx.conf` 反向代理
后端并透传 SSE。

```bash
cd ../docker
docker compose build
docker compose up -d
# 前端 http://localhost:8038/ ，后端 http://localhost:8008/
```
