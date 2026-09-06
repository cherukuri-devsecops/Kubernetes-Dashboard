# syntax=docker/dockerfile:1

FROM node:22-alpine AS build

WORKDIR /app

# Manifests first: editing src/ then leaves the install layer cached.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .

# Vite inlines VITE_* variables at build time, so the API base is baked into the
# bundle here. Empty means same-origin — served by the nginx /api proxy below.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.29-alpine

# Templates land in conf.d at start-up, after envsubst fills in BACKEND_ORIGIN.
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# Compose's service name; Kubernetes overrides this with the backend Service.
ENV BACKEND_ORIGIN=http://backend:8000

EXPOSE 80

# No HEALTHCHECK here on purpose: podman builds OCI images, which drop the
# instruction. The check lives on the compose service, like every other service
# in this stack; Kubernetes uses the chart's readiness probe.
