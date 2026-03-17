#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${MZ_AGENT_WEB_HOST:-127.0.0.1}"
PORT="${MZ_AGENT_WEB_PORT:-8000}"
PROFILE="${MZ_AGENT_WEB_PROFILE:-}"
LIVE_LLM="${MZ_AGENT_WEB_LIVE_LLM:-1}"
STM_PATH="${MZ_AGENT_WEB_STM_PATH:-.mz_agent/web_stm.json}"
PYTHON_BIN="${MZ_AGENT_WEB_PYTHON:-$ROOT_DIR/.venv/bin/python}"
ENV_FILE="${MZ_AGENT_WEB_ENV_FILE:-$ROOT_DIR/.env}"

usage() {
  cat <<'EOF'
用法：
  ./scripts/start_web.sh [--host 127.0.0.1] [--port 8000] [--profile profile_name] [--env-file /path/to/.env] [--no-live-llm]

环境变量：
  MZ_AGENT_WEB_HOST        监听地址，默认 127.0.0.1
  MZ_AGENT_WEB_PORT        监听端口，默认 8000
  MZ_AGENT_WEB_PROFILE     默认启用的配置方案名称
  MZ_AGENT_WEB_LIVE_LLM    是否启用真实 LLM，默认 1
  MZ_AGENT_WEB_STM_PATH    Web 会话持久化路径，默认 .mz_agent/web_stm.json
  MZ_AGENT_WEB_PYTHON      Python 解释器路径，默认 .venv/bin/python
  MZ_AGENT_WEB_ENV_FILE    启动前自动加载的环境文件，默认 <repo>/.env
EOF
}

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
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --stm-path)
      STM_PATH="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --live-llm)
      LIVE_LLM="1"
      shift
      ;;
    --no-live-llm)
      LIVE_LLM="0"
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
  cat >&2 <<EOF
未找到可执行 Python：$PYTHON_BIN
请先在仓库根目录执行：
  python3 -m venv .venv
  . .venv/bin/activate
  python -m pip install -e .
EOF
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

cd "$ROOT_DIR"

echo "MzAgent Web 即将启动："
echo "  root      = $ROOT_DIR"
echo "  host      = $HOST"
echo "  port      = $PORT"
echo "  profile   = ${PROFILE:-<默认方案>}"
echo "  live_llm  = $LIVE_LLM"
echo "  stm_path  = $STM_PATH"
echo "  env_file  = $ENV_FILE"
echo
echo "浏览器访问：http://$HOST:$PORT"

ARGS=(
  -m mz_agent.web.server
  --host "$HOST"
  --port "$PORT"
  --stm-path "$STM_PATH"
)

if [[ "$LIVE_LLM" == "1" ]]; then
  ARGS+=(--live-llm)
fi

if [[ -n "$PROFILE" ]]; then
  ARGS+=(--llm-profile "$PROFILE")
fi

exec "$PYTHON_BIN" "${ARGS[@]}"
