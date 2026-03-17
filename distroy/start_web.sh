#!/usr/bin/env bash
# MzAgent Web 控制台启动脚本
cd "$(dirname "$0")" || exit 1
exec ./.venv/bin/python -m mz_agent.web.server --host 0.0.0.0 --port 8199
