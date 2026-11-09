# Data-Copilot Vue 3 Frontend

## 运行

```bash
cd vue-front
npm install
npm run dev
```

访问 `http://localhost:5173/`

## 前置条件

确保后端已启动（默认端口 8008）：

```bash
python main.py
```

确保 `vue-front/.env` 已配置 `VITE_SERVER_URL`（开发代理目标，`vite.config.js` 读取，缺失时代理目标为 undefined），可选配置 `VITE_API_BASE`（API 请求基地址，默认 `/api`）。

Vite 开发服务器会自动将 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 代理到后端。