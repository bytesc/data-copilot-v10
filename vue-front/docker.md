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

挂载 `src` 目录可实现热更新；`vite.config.js`、`index.html`、`public/` 等其它文件不在挂载范围内，这些改动需要重建镜像。开发代理目标由 `.env` 的 `DEV_PROXY_TARGET` 决定（非 `VITE_` 前缀，不会注入客户端产物）。

## 生产部署（Docker Compose）

实际生产用的前端镜像由 `../docker/Dockerfile.frontend` **多阶段构建**：先在
`node:20-alpine` 阶段构建 `dist/`，再复制进 `nginx:alpine`，因此**不需要**预先在宿主机构建
`dist/`（`dist/` 已被 gitignore）。前端容器监听 `8038`，由 `../docker/nginx.conf` 反向代理
后端并透传 SSE。

> 前端产物使用**同源相对地址**访问 API，构建时**不固化后端地址**，换服务器部署无需重新构建前端。
> 后端生成的绝对 URL（文档下载链接、聊天正文中的图表图片、交互图/CSV 链接、静态地图等）由
> `STATIC_PATH` 决定，跨机访问时必须设为浏览器可达的前端地址，详见
> [`../docs/deployment.md`](../docs/deployment.md)。

```bash
cd ../docker
docker compose build
docker compose up -d
# 前端 http://localhost:8038/ ，后端 http://localhost:8008/
```
