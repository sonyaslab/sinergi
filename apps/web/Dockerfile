# Bangun SPA lalu sajikan dengan Nginx (konfigurasi di deploy/nginx/sinergi.conf, dipasang lewat compose).
FROM node:22.12.0-bookworm-slim AS bangun
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27.3-alpine
COPY --from=bangun /web/dist /usr/share/nginx/html
