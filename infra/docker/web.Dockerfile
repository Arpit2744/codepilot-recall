# Web (Next.js) service image. Build context: repository root.
# Node >=22.22.2 required by jsdom 30 / vitest 5 engines.
#
# npm workspaces hoist dependencies into the ROOT node_modules and symlink
# workspace packages there (@codepilot/contracts -> packages/contracts);
# apps/web/node_modules typically does not exist. The stages below copy the
# root install and the workspace sources it links to — never a per-workspace
# node_modules.
#
# NEXT_PUBLIC_API_BASE_URL defaults to EMPTY: browser requests use relative
# /api/v1 paths through the same-origin proxy (route.ts), so cookies are
# first-party. An explicit build arg (e.g. docker-compose passes
# http://localhost:8000 for local development) overrides it.

FROM node:24-alpine AS deps
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/contracts/package.json packages/contracts/
RUN npm ci --no-fund --no-audit

FROM node:24-alpine AS build
WORKDIR /build
COPY --from=deps /build/node_modules ./node_modules
COPY package.json ./
COPY packages/contracts ./packages/contracts
COPY apps/web ./apps/web
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN cd apps/web && npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# `output: standalone` in a workspace build keeps the app under apps/web.
COPY --from=build /build/apps/web/.next/standalone ./
COPY --from=build /build/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /build/apps/web/public ./apps/web/public

USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
