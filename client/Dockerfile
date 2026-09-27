# Nexus client (Vite SPA + client/server.ts) — Cloud Run image (see /DEPLOY.md).
FROM node:22-bookworm-slim AS build
# better-sqlite3 falls back to a source build if no prebuilt binary matches.
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22-bookworm-slim
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/package.json ./
COPY --from=build /app/data/database.json ./data/database.json
# BACKEND_URL (runtime env) is where server.ts proxies /backend/* to.
CMD ["node", "dist/server.cjs"]
