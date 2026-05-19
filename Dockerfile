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

# Copy pre-built admin UI from stage 1
COPY --from=admin-builder /build/admin-dist ./admin-dist

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
