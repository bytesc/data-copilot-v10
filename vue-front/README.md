# Data-Copilot Vue 3 Frontend

前端有两种使用方式（都**不是仓库级部署**；把前端 + 后端整体部署见 [`../docs/deployment.md`](../docs/deployment.md)）：

- **npm 方式**（本文）：`npm run dev` 起开发服务器，或 `npm run build` 产出 `dist/` 交给前端服务。
- **docker 方式**：用本目录的 Dockerfile 构建前端镜像，见 [`docker.md`](docker.md)。

> 文中端口都只是**默认值，均可修改**。

---

## npm 方式

### 开发服务器：`npm run dev`

```bash
cd vue-front
npm install
npm run dev
```

访问 `http://localhost:<前端端口>/`（默认 `5173`；跨机访问加 `-- --host`）。

**前置条件**

- 后端已启动（见 [`../docs/deployment.md`](../docs/deployment.md)）。
- `vue-front/.env` 的 `DEV_PROXY_TARGET` 指向后端实际 `host:port`（默认 `http://127.0.0.1:<后端端口>`，即 `http://127.0.0.1:8008`）；它不会自动跟随 `config.yaml` 的 `server_port`，后端不在本机或改过端口都要改。

Vite 开发服务器会把 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 代理到后端。

### 构建产物：`npm run build`

```bash
cd vue-front
npm install
npm run build        # 产出 dist/
```

`dist/` 由前端服务提供：`front.py` 或 nginx（见 [`../docs/deployment.md`](../docs/deployment.md)）。
生产构建**不使用** `DEV_PROXY_TARGET`，浏览器端走**同源相对地址**，因此换服务器不用重建前端。

### `vue-front/.env`

```env
VITE_API_BASE=/api
DEV_PROXY_TARGET=http://127.0.0.1:8008
```

- `VITE_API_BASE`：API 请求基地址，默认 `/api`。
- `DEV_PROXY_TARGET`：仅 `npm run dev` 使用（`vite.config.js` 读取，非 `VITE_` 前缀、不会注入客户端产物），缺失时开发代理目标为 undefined。
