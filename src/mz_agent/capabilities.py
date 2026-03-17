"""MzAgent Web 能力注册表存储。"""

from __future__ import annotations

from typing import Literal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .config import load_runtime_settings

CapabilityType = Literal["tool", "mcp", "skill"]


class CapabilityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    enabled: bool = True
    endpoint: str | None = None
    transport: str | None = None
    command: str | None = None
    entry: str | None = None


class CapabilityRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: list[CapabilityItem] = Field(default_factory=list)
    mcp: list[CapabilityItem] = Field(default_factory=list)
    skills: list[CapabilityItem] = Field(default_factory=list)

    def items_for(self, capability_type: CapabilityType) -> list[CapabilityItem]:
        if capability_type == "tool":
            return list(self.tools)
        if capability_type == "mcp":
            return list(self.mcp)
        return list(self.skills)

    def upsert(self, *, capability_type: CapabilityType, item: CapabilityItem) -> "CapabilityRegistry":
        items = self.items_for(capability_type)
        item_map = {capability.name: capability for capability in items}
        item_map[item.name] = item
        ordered_items = sorted(item_map.values(), key=lambda capability: capability.name)
        return self._with_items(capability_type=capability_type, items=ordered_items)

    def delete(self, *, capability_type: CapabilityType, name: str) -> "CapabilityRegistry":
        items = self.items_for(capability_type)
        item_map = {capability.name: capability for capability in items}
        if name not in item_map:
            raise ValueError(f"未找到能力项：{name}")
        item_map.pop(name)
        ordered_items = sorted(item_map.values(), key=lambda capability: capability.name)
        return self._with_items(capability_type=capability_type, items=ordered_items)

    def toggle(self, *, capability_type: CapabilityType, name: str) -> tuple["CapabilityRegistry", CapabilityItem]:
        items = self.items_for(capability_type)
        item_map = {capability.name: capability for capability in items}
        item = item_map.get(name)
        if item is None:
            raise ValueError(f"未找到能力项：{name}")
        updated = item.model_copy(update={"enabled": not item.enabled})
        item_map[name] = updated
        ordered_items = sorted(item_map.values(), key=lambda capability: capability.name)
        return (self._with_items(capability_type=capability_type, items=ordered_items), updated)

    def _with_items(
        self,
        *,
        capability_type: CapabilityType,
        items: list[CapabilityItem],
    ) -> "CapabilityRegistry":
        if capability_type == "tool":
            return self.model_copy(update={"tools": items})
        if capability_type == "mcp":
            return self.model_copy(update={"mcp": items})
        return self.model_copy(update={"skills": items})


def load_capability_registry(*, project_root: Path) -> CapabilityRegistry:
    storage_path = _storage_path(project_root=project_root)
    if storage_path.exists():
        return CapabilityRegistry.model_validate_json(storage_path.read_text(encoding="utf-8"))
    return build_default_capability_registry(project_root=project_root)


def save_capability_registry(*, project_root: Path, registry: CapabilityRegistry) -> None:
    storage_path = _storage_path(project_root=project_root)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(
        registry.model_dump_json(indent=2),
        encoding="utf-8",
    )


def build_default_capability_registry(*, project_root: Path) -> CapabilityRegistry:
    runtime_settings = load_runtime_settings(project_root)
    mcp_items: list[CapabilityItem] = []
    for server in sorted(runtime_settings.mcp_servers.values(), key=lambda item: item.name):
        default_tool_name = "zhi" if server.name == "cunzhi" else None
        capability_name = f"{server.name}:{default_tool_name}" if default_tool_name else server.name
        mcp_items.append(
            CapabilityItem(
                name=capability_name,
                description=f"{server.name} MCP 能力入口",
                enabled=True,
                transport=server.transport_type,
                command=server.command,
            )
        )

    return CapabilityRegistry(
        tools=[
            CapabilityItem(
                name="search_docs",
                description="搜索文档",
                enabled=True,
            )
        ],
        mcp=mcp_items,
        skills=[],
    )


def _storage_path(*, project_root: Path) -> Path:
    return project_root / ".mz_agent" / "capabilities.json"
