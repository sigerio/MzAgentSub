#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${MZ_AGENT_PREVIEW_HOST:-127.0.0.1}"
PORT="${MZ_AGENT_PREVIEW_PORT:-8765}"
OUT_FILE="${MZ_AGENT_PREVIEW_OUT:-/tmp/mz-agent-web-preview.png}"
STM_PATH="${MZ_AGENT_PREVIEW_STM_PATH:-/tmp/mz-agent-preview-stm.json}"
PYTHON_BIN="${MZ_AGENT_WEB_PYTHON:-$ROOT_DIR/.venv/bin/python}"
START_SCRIPT="$ROOT_DIR/scripts/start_web.sh"
PREVIEW_SCRIPT="$ROOT_DIR/scripts/playwright_preview.py"

usage() {
  cat <<'EOF'
用法：
  ./scripts/preview_web.sh [--host 127.0.0.1] [--port 8765] [--out /tmp/preview.png] [--full-page]

说明：
  该脚本会先启动本地 Web，再使用 Playwright 生成截图，最后自动关闭服务。
EOF
}

FULL_PAGE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --out)
      OUT_FILE="$2"
      shift 2
      ;;
    --stm-path)
      STM_PATH="$2"
      shift 2
      ;;
    --full-page)
      FULL_PAGE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "未找到可执行 Python：$PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -x "$START_SCRIPT" ]]; then
  echo "未找到启动脚本：$START_SCRIPT" >&2
  exit 1
fi

SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

"$START_SCRIPT" --host "$HOST" --port "$PORT" --no-live-llm --stm-path "$STM_PATH" &
SERVER_PID=$!

"$PYTHON_BIN" - <<PY
import sys
import time
from urllib.request import urlopen

url = "http://$HOST:$PORT/"
deadline = time.time() + 20
last_error = None
while time.time() < deadline:
    try:
        with urlopen(url, timeout=2) as response:
            if response.status == 200:
                print(f"页面已就绪：{url}")
                sys.exit(0)
    except Exception as error:
        last_error = error
        time.sleep(0.5)

print(f"页面启动失败：{last_error}", file=sys.stderr)
sys.exit(1)
PY

PREVIEW_ARGS=(
  "$PREVIEW_SCRIPT"
  --url "http://$HOST:$PORT/"
  --out "$OUT_FILE"
)

if [[ "$FULL_PAGE" == "1" ]]; then
  PREVIEW_ARGS+=(--full-page)
fi

"$PYTHON_BIN" "${PREVIEW_ARGS[@]}"
