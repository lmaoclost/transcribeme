FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE=__LAN_AUTO__
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
COPY package.json yarn.lock ./
RUN corepack enable && yarn install --frozen-lockfile
COPY . ./
RUN yarn build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# standalone server + traced prod deps only (no devDeps, no yarn needed at runtime)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# NOTE: no public/ dir in this project; add COPY back if one is created
EXPOSE 3000
CMD ["node", "server.js"]
