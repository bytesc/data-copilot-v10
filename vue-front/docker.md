## Dockerfile

构建镜像，生成 `dist` 产物（无服务端，仅编译）。

```bash
docker build -t vue-front-build .
```

产物在镜像内 `/app/dist` 路径，可通过 `docker cp` 或多阶段构建提取。

---

## Dockerfile.dev

开发模式，运行 `npm run dev`（Vite HMR），暴露 5173 端口。

```bash
docker build -f Dockerfile.dev -t vue-front-dev .
docker run -p 5173:5173 -v ${PWD}/src:/app/src vue-front-dev
```

挂载 `src` 目录可实现热更新。