#!/usr/bin/env bash
# ============================================================
#  Auto-deploy: pull main + rebuild + restart Docker
#  Dipanggil oleh cron/timer tiap beberapa menit.
#  Aman: .env & data/ tidak di git, jadi tidak ketimpa.
# ============================================================
set -euo pipefail

# cron punya PATH minimal -> set eksplisit biar docker & git ketemu
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO_DIR="/home/user/explore"
BRANCH="main"
LOG_FILE="$REPO_DIR/deploy.log"

cd "$REPO_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# --- pastikan di branch yang benar ---
git checkout "$BRANCH" >/dev/null 2>&1 || {
  log "GAGAL: tidak bisa checkout $BRANCH"
  exit 1
}

# --- ambil update dari remote ---
if [ "${SKIP_FETCH:-0}" != "1" ]; then
  git fetch origin "$BRANCH" --quiet
fi

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
  # tidak ada perubahan; keluar tanpa log (biar log tidak spam)
  exit 0
fi

log "Ada commit baru: ${LOCAL:0:7} -> ${REMOTE:0:7}. Mulai deploy."

# --- pull (fast-forward only, jangan bikin merge) ---
if ! git pull --ff-only origin "$BRANCH" >>"$LOG_FILE" 2>&1; then
  log "GAGAL: git pull tidak bisa fast-forward. Cek konflik manual."
  exit 1
fi

# --- rebuild + restart ---
if docker compose up -d --build >>"$LOG_FILE" 2>&1; then
  log "SUKSES deploy commit ${REMOTE:0:7}."
else
  log "GAGAL: docker compose up --build error. Cek log di atas."
  exit 1
fi
