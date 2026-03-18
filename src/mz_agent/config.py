"""MzAgent 运行时配置装载。"""

from __future__ import annotations
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .llm_profiles import (
    DEFAULT_API_MODE,
    LLMConnection,
    LLMProfile,
    load_profile_store,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str | None = None
    model_id: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    api_mode: str = DEFAULT_API_MODE
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)
    timeout: int = Field(default=60, ge=1)

    def is_configured(self) -> bool:
        return bool(self.model_id and self.api_key and self.base_url)

    @classmethod
    def from_profile(
        cls,
        *,
        profile: LLMProfile,
        connection: LLMConnection,
    ) -> "LLMSettings":
        return cls(
            profile_name=profile.profile_name,
            model_id=profile.model_name,
            api_key=connection.api_key,
            base_url=connection.base_url,
            api_mode=profile.api_mode,
            extra_headers=dict(profile.extra_headers),
            enabled_capabilities=list(profile.enabled_capabilities),
            timeout=connection.timeout,
        )


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
    active_profile_name: str | None = None
    llm_profiles: dict[str, LLMProfile] = Field(default_factory=dict)
    mcp_servers: dict[str, MCPServerSettings] = Field(default_factory=dict)


def load_runtime_settings(
    project_root: str | Path | None = None,
    *,
    profile_name: str | None = None,
) -> RuntimeSettings:
    root = discover_project_root(project_root)
    profile_store = load_profile_store(project_root=root)
    selected_profile_name = profile_name or profile_store.resolve_active_profile_name()
    if not selected_profile_name:
        raise ValueError("当前无配置方案，请先配置 NewAPI 连接并添加模型。")
    if profile_store.connection is None or not profile_store.connection.is_configured():
        raise ValueError("当前未配置 NewAPI 连接，请先填写 base_url 与 api_key。")
    selected_profile = profile_store.require(selected_profile_name)
    llm = LLMSettings.from_profile(
        profile=selected_profile,
        connection=profile_store.connection,
    )

    pyproject_data = load_pyproject(root / "pyproject.toml")
    mcp_servers = parse_mcp_servers(pyproject_data)
    return RuntimeSettings(
        project_root=root,
        llm=llm,
        active_profile_name=profile_store.resolve_active_profile_name(),
        llm_profiles=profile_store.profile_map(),
        mcp_servers=mcp_servers,
    )


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
