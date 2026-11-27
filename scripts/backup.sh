#!/usr/bin/env bash
# Back up or restore the database of the running service.
#   ./scripts/backup.sh save                 writes backups/app-<date>-<time>.db on this machine
#   ./scripts/backup.sh restore <file>       replaces the live database with that copy
# The copy is a consistent snapshot taken while the service runs (SQLite's online backup).
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  save)
    mkdir -p backups
    target="backups/app-$(date +%Y%m%d-%H%M%S).db"
    docker compose exec -T api python -m app.backup save /tmp/backup.db
    docker compose cp api:/tmp/backup.db "$target"
    echo "backup written to $target"
    ;;
  restore)
    [ -f "${2:-}" ] || { echo "usage: $0 restore <file>" >&2; exit 2; }
    docker compose cp "$2" api:/tmp/restore.db
    docker compose exec -T api python -m app.backup restore /tmp/restore.db
    ;;
  *)
    echo "usage: $0 save | restore <file>" >&2
    exit 2
    ;;
esac
