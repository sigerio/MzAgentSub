"""MzAgent 运行时配置装载。"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    timeout: int = Field(default=60, ge=1)

    def is_configured(self) -> bool:
        return bool(self.model_id and self.api_key and self.base_url)


class MCPServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    transport_type: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    tool_timeout_sec: float = Field(default=600.0, gt=0)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_root: Path
    llm: LLMSettings
    mcp_servers: dict[str, MCPServerSettings] = Field(default_factory=dict)


def load_runtime_settings(project_root: str | Path | None = None) -> RuntimeSettings:
    root = discover_project_root(project_root)
    env_values = load_env_file(root / ".env")

    llm = LLMSettings(
        model_id=_pick_value("LLM_MODEL_ID", env_values),
        api_key=_pick_value("LLM_API_KEY", env_values),
        base_url=_pick_value("LLM_BASE_URL", env_values),
        timeout=_read_timeout(env_values),
    )

    pyproject_data = load_pyproject(root / "pyproject.toml")
    mcp_servers = parse_mcp_servers(pyproject_data)
    return RuntimeSettings(project_root=root, llm=llm, mcp_servers=mcp_servers)


def discover_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        root = Path(project_root).expanduser().resolve()
        if not (root / "pyproject.toml").exists():
            raise FileNotFoundError(f"未找到 pyproject.toml：{root}")
        return root

    search_points = [
        Path.cwd(),
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3],
    ]
    for start in search_points:
        candidate = start
        while True:
            if (candidate / "pyproject.toml").exists():
                return candidate
            if candidate.parent == candidate:
                break
            candidate = candidate.parent

    raise FileNotFoundError("未找到 MzAgentSub 项目根目录。")


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        values[key] = value
    return values


def load_pyproject(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_mcp_servers(pyproject_data: dict[str, object]) -> dict[str, MCPServerSettings]:
    raw_servers = pyproject_data.get("mcp_servers")
    if not isinstance(raw_servers, dict):
        return {}

    servers: dict[str, MCPServerSettings] = {}
    for name, raw_server in raw_servers.items():
        if not isinstance(name, str) or not isinstance(raw_server, dict):
            continue
        args = raw_server.get("args", [])
        env = raw_server.get("env", {})
        servers[name] = MCPServerSettings(
            name=name,
            transport_type=str(raw_server.get("type", "stdio")),
            command=str(raw_server.get("command", "")),
            args=[str(item) for item in args] if isinstance(args, list) else [],
            env={
                str(key): str(value)
                for key, value in env.items()
            }
            if isinstance(env, dict)
            else {},
            tool_timeout_sec=float(raw_server.get("tool_timeout_sec", 600.0)),
        )
    return servers


def _pick_value(key: str, env_values: dict[str, str]) -> str | None:
    current = os.getenv(key)
    if current:
        return current
    value = env_values.get(key)
    return value or None


def _read_timeout(env_values: dict[str, str]) -> int:
    raw_timeout = _pick_value("LLM_TIMEOUT", env_values)
    if raw_timeout is None:
        return 60
    try:
        timeout = int(raw_timeout)
    except ValueError:
        return 60
    return timeout if timeout > 0 else 60
