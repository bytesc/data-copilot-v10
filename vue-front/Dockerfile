# Build-only image: produces /app/dist for `docker cp` extraction (see docker.md).
# It intentionally has no CMD/ENTRYPOINT and serves no traffic; the production
# image is docker/Dockerfile.frontend (multi-stage build + nginx).
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY . .

RUN npm run build