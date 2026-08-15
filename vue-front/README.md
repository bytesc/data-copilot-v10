# Data-Copilot Vue 3 Frontend

## 运行

```bash
cd vue-front
npm install
npm run dev
```

访问 `http://localhost:5173/`

## 前置条件

确保后端已启动（默认端口 8009）：

```bash
python main.py
```

Vite 开发服务器会自动将 `/api`、`/upload-csv`、`/upload-txt`、`/tmp_imgs` 代理到后端。