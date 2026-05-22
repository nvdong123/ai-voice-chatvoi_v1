#!/bin/sh
# Seed default data files into the persistent volume on first run.
# If Coolify (or any orchestrator) mounts /app/data as a volume, the files
# baked into the image are shadowed. This script copies them once if missing.

SEED_DIR="/app/data_seed"
DATA_DIR="/app/data"

mkdir -p "$DATA_DIR"

for f in scenes.json nodes.json; do
  if [ ! -f "$DATA_DIR/$f" ] && [ -f "$SEED_DIR/$f" ]; then
    echo "[entrypoint] Seeding $f into $DATA_DIR/"
    cp "$SEED_DIR/$f" "$DATA_DIR/$f"
  fi
done

exec uvicorn main:app --host 0.0.0.0 --port 8000
