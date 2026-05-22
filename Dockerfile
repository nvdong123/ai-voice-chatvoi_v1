# ── Stage 1: Build React admin UI ────────────────────────────────────────────
FROM node:22-slim AS admin-builder

WORKDIR /build/admin
COPY admin/package*.json ./
RUN npm ci --prefer-offline

COPY admin/ ./
RUN npm run build          # outputs to ../admin-dist (vite outDir)

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Seed data — stored separately so a volume mount on /app/data doesn't
# shadow the bundled scenes.json / nodes.json on first deploy.
COPY data/ /app/data_seed/

# Copy pre-built admin UI from stage 1
COPY --from=admin-builder /build/admin-dist ./admin-dist

EXPOSE 8000

RUN chmod +x /app/entrypoint.sh
CMD ["/app/entrypoint.sh"]
