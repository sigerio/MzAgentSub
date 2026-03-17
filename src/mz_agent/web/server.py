"""MzAgent Web 服务启动入口。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from ..app import RuntimeOptions
from .app import create_app


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 MzAgent 最小 Web 服务。")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址。")
    parser.add_argument("--port", type=int, default=8000, help="监听端口。")
    parser.add_argument("--stm-path", default=".mz_agent/web_stm.json", help="STM 持久化文件路径。")
    parser.add_argument("--live-llm", action="store_true", help="启用真实 LLM 调用。")
    parser.add_argument("--session-id", default="sess_web", help="Web 默认会话标识。")
    parser.add_argument("--request-prefix", default="req_web", help="请求标识前缀。")
    parser.add_argument("--trace-prefix", default="trace_web", help="追踪标识前缀。")
    parser.add_argument("--draft-answer", default="任务已收束", help="finish 动作的草稿答复。")
    parser.add_argument("--llm-profile", default="", help="默认使用的 LLM 配置方案名称。")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    options = RuntimeOptions.from_namespace(args)
    project_root = Path(__file__).resolve().parents[3]
    app = create_app(project_root=project_root, options=options)

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("未安装 uvicorn，请先重新执行 `python -m pip install -e .`。") from exc

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
