# 前端镜像（多阶段：构建 + nginx 静态服务）
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN npm i -g pnpm && pnpm install --frozen-lockfile || pnpm install
COPY . .
RUN pnpm build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# 代理 /api 到 backend
RUN printf 'server {\n  listen 80;\n  location / { root /usr/share/nginx/html; try_files $uri /index.html; }\n  location /api { proxy_pass http://backend:8000; }\n}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
