# 开发阶段
FROM node:20-alpine AS development
WORKDIR /app
ENV TZ=Asia/Shanghai

# 固定 pnpm 版本，和 package.json 的 packageManager 保持一致
ARG PNPM_VERSION=10.11.0
RUN npm install -g pnpm@${PNPM_VERSION}

# 复制 package.json 和 pnpm-lock.yaml
COPY ./web/package*.json ./
COPY ./web/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install --registry=https://registry.npmmirror.com

# 复制源代码
COPY ./web .

# 暴露端口
EXPOSE 5173

# 启动开发服务器的命令在 docker-compose 文件中定义


# 生产构建阶段
FROM node:20-alpine AS build-stage
WORKDIR /app

# 固定 pnpm 版本，避免 pnpm@latest 和 Node 20 不兼容
ARG PNPM_VERSION=10.11.0
RUN npm install -g pnpm@${PNPM_VERSION}

# 复制依赖文件
COPY ./web/package*.json ./
COPY ./web/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install --frozen-lockfile --registry=https://registry.npmmirror.com

# 复制源代码并构建
COPY ./web .
RUN pnpm run build


# 生产环境运行阶段
FROM nginx:alpine AS production
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY ./docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY ./docker/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]