#!/bin/bash
# SessionStart hook for Claude Code on the web.
# Installs root, frontend (Node) and backend (Python/uv) dependencies so that
# tests and tooling work inside remote sessions.
set -euo pipefail

# Only run in the remote (Claude Code on the web) environment.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Run asynchronously so the session starts immediately while dependencies
# install in the background. Note: there is a brief window at startup where
# deps may not yet be ready (e.g. running tests in the first moments).
echo '{"async": true, "asyncTimeout": 600000}'

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_DIR"

echo "[session-start] Installing root Node dependencies..."
npm install

echo "[session-start] Installing frontend Node dependencies..."
(cd frontend && npm install)

# Backend Python dependencies are managed with uv (see backend/pyproject.toml).
if command -v uv >/dev/null 2>&1; then
  echo "[session-start] Syncing backend Python dependencies (incl. dev) with uv..."
  (cd backend && uv sync --extra dev)
else
  echo "[session-start] WARNING: 'uv' not found on PATH; skipping backend dependency install."
fi

echo "[session-start] Dependency installation complete."
