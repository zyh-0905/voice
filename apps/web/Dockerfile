FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
# VITE_USE_MOCK 是构建期变量:不传时 vite 会把它当未定义,镜像恒为 mock——
# 后端真栈在跑、前端却从不调用它。默认 false(真实 API,同源 /api/v1 走 nginx 反代),
# compose 通过 build args 注入,CI 与本地 npm run dev 不受影响。
ARG VITE_USE_MOCK=false
ENV VITE_USE_MOCK=${VITE_USE_MOCK}
RUN npm run build
FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080


