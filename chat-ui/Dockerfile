# ---- build ----
FROM node:26-alpine AS build
WORKDIR /src

# Lockfile first so source edits do not invalidate the install layer.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# ---- runtime ----
# Unprivileged nginx: listens on 8080 and runs as uid 101, no root.
FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/ | grep -q '<div id="root">' || exit 1
