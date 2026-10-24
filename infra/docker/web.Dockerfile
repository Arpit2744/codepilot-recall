# Web (Next.js) service image. Build context: repository root.
# Node >=22.22.2 required by jsdom 30 / vitest 5 engines.

FROM node:24-alpine AS deps
WORKDIR /build
COPY package.json ./
COPY apps/web/package.json apps/web/
COPY packages/contracts/package.json packages/contracts/
RUN npm install --workspace @codepilot/web --include-workspace-root

FROM node:24-alpine AS build
WORKDIR /build
COPY --from=deps /build/node_modules ./node_modules
COPY --from=deps /build/apps/web/node_modules ./apps/web/node_modules
COPY package.json ./
COPY packages/contracts ./packages/contracts
COPY apps/web ./apps/web
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
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
