"""MzAgent LLM 配置方案存储。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROFILE_STORAGE_RELATIVE_PATH = Path(".mz_agent/llm_profiles.json")
DEFAULT_API_MODE = "openai-responses"
SUPPORTED_API_MODES = (
    "openai-responses",
    "openai-completions",
    "anthropic-messages",
)


class LLMConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None
    timeout: int = Field(default=60, ge=1)

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def masked_api_key(self) -> str | None:
        if not self.api_key:
            return None
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}***{self.api_key[-4:]}"


class LLMProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    model_name: str
    api_mode: str = DEFAULT_API_MODE
    display_name: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)

    @field_validator("api_mode", mode="before")
    @classmethod
    def _validate_api_mode(cls, value: object) -> str:
        return normalize_llm_api_mode(value)

    def resolved_display_name(self) -> str:
        return self.display_name or self.profile_name


class LLMProfileStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: LLMConnection | None = None
    active_profile_name: str | None = None
    profiles: list[LLMProfile] = Field(default_factory=list)

    def profile_map(self) -> dict[str, LLMProfile]:
        return {profile.profile_name: profile for profile in self.profiles}

    def get(self, profile_name: str) -> LLMProfile | None:
        return self.profile_map().get(profile_name)

    def require(self, profile_name: str) -> LLMProfile:
        profile = self.get(profile_name)
        if profile is None:
            raise ValueError(f"未找到模型方案：{profile_name}")
        return profile

    def resolve_active_profile_name(self) -> str | None:
        profile_map = self.profile_map()
        if self.active_profile_name and self.active_profile_name in profile_map:
            return self.active_profile_name
        if not self.profiles:
            return None
        return self.profiles[0].profile_name

    def normalized(self) -> "LLMProfileStore":
        return LLMProfileStore(
            connection=self.connection,
            active_profile_name=self.resolve_active_profile_name(),
            profiles=list(self.profiles),
        )

    def set_connection(self, connection: LLMConnection) -> "LLMProfileStore":
        return LLMProfileStore(
            connection=connection,
            active_profile_name=self.resolve_active_profile_name(),
            profiles=list(self.profiles),
        )

    def upsert(self, profile: LLMProfile) -> "LLMProfileStore":
        profile_map = self.profile_map()
        profile_map[profile.profile_name] = profile
        ordered_profiles = [
            profile_map[name]
            for name in sorted(profile_map.keys(), key=str.lower)
        ]
        active_profile_name = self.active_profile_name or profile.profile_name
        if active_profile_name not in profile_map:
            active_profile_name = profile.profile_name
        return LLMProfileStore(
            connection=self.connection,
            active_profile_name=active_profile_name,
            profiles=ordered_profiles,
        )

    def delete(self, profile_name: str) -> "LLMProfileStore":
        profile_map = self.profile_map()
        if profile_name not in profile_map:
            raise ValueError(f"未找到模型方案：{profile_name}")
        profile_map.pop(profile_name)
        ordered_profiles = [
            profile_map[name]
            for name in sorted(profile_map.keys(), key=str.lower)
        ]
        active_profile_name = self.active_profile_name
        if active_profile_name == profile_name:
            active_profile_name = ordered_profiles[0].profile_name if ordered_profiles else None
        return LLMProfileStore(
            connection=self.connection,
            active_profile_name=active_profile_name,
            profiles=ordered_profiles,
        )

    def activate(self, profile_name: str) -> "LLMProfileStore":
        self.require(profile_name)
        return LLMProfileStore(
            connection=self.connection,
            active_profile_name=profile_name,
            profiles=list(self.profiles),
        )


def load_profile_store(
    *,
    project_root: Path,
    env_values: dict[str, str] | None = None,
) -> LLMProfileStore:
    del env_values
    storage_path = project_root / PROFILE_STORAGE_RELATIVE_PATH
    if not storage_path.exists():
        return LLMProfileStore()

    raw_text = storage_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return LLMProfileStore()

    raw_payload = json.loads(raw_text)
    return _load_store_from_payload(raw_payload).normalized()


def save_profile_store(*, project_root: Path, store: LLMProfileStore) -> None:
    storage_path = project_root / PROFILE_STORAGE_RELATIVE_PATH
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(
        json.dumps(store.normalized().model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_store_from_payload(raw_payload: Any) -> LLMProfileStore:
    if not isinstance(raw_payload, dict):
        raise ValueError("LLM 配置文件格式不正确。")

    if "connection" in raw_payload or "active_profile_name" in raw_payload:
        return LLMProfileStore.model_validate(raw_payload)

    return _migrate_legacy_store(raw_payload)


def _migrate_legacy_store(raw_payload: dict[str, Any]) -> LLMProfileStore:
    raw_profiles = raw_payload.get("profiles", [])
    if not isinstance(raw_profiles, list):
        return LLMProfileStore()

    active_profile_name = raw_payload.get("default_profile_name")
    active_profile: dict[str, Any] | None = None
    if isinstance(active_profile_name, str):
        for item in raw_profiles:
            if isinstance(item, dict) and item.get("profile_name") == active_profile_name:
                active_profile = item
                break
    if active_profile is None:
        for item in raw_profiles:
            if isinstance(item, dict):
                active_profile = item
                break

    connection = _build_legacy_connection(active_profile)
    profiles: list[LLMProfile] = []
    for item in raw_profiles:
        if not isinstance(item, dict):
            continue
        profile_name = str(item.get("profile_name") or "").strip()
        model_name = str(item.get("default_model") or item.get("model_name") or "").strip()
        if not profile_name or not model_name:
            continue
        profiles.append(
            LLMProfile(
                profile_name=profile_name,
                display_name=_normalize_optional_text(item.get("display_name")),
                model_name=model_name,
                api_mode=item.get("api_mode"),
                extra_headers=_normalize_string_dict(item.get("extra_headers")),
                enabled_capabilities=_normalize_string_list(item.get("enabled_capabilities")),
            )
        )

    return LLMProfileStore(
        connection=connection,
        active_profile_name=active_profile_name if isinstance(active_profile_name, str) else None,
        profiles=profiles,
    )


def _build_legacy_connection(raw_profile: dict[str, Any] | None) -> LLMConnection | None:
    if raw_profile is None:
        return None
    base_url = _normalize_optional_text(raw_profile.get("base_url"))
    api_key = _normalize_optional_text(raw_profile.get("api_key"))
    timeout = raw_profile.get("timeout", 60)
    try:
        parsed_timeout = int(timeout)
    except (TypeError, ValueError):
        parsed_timeout = 60
    connection = LLMConnection(
        base_url=base_url,
        api_key=api_key,
        timeout=parsed_timeout if parsed_timeout > 0 else 60,
    )
    if not connection.base_url and not connection.api_key:
        return None
    return connection


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
    }


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def normalize_llm_api_mode(value: object) -> str:
    if not isinstance(value, str):
        return DEFAULT_API_MODE

    normalized = value.strip().lower()
    alias_map = {
        "responses": "openai-responses",
        "response": "openai-responses",
        "openai-responses": "openai-responses",
        "openai_response": "openai-responses",
        "openai-response": "openai-responses",
        "chat": "openai-completions",
        "chat-completions": "openai-completions",
        "chat_completions": "openai-completions",
        "completions": "openai-completions",
        "openai": "openai-completions",
        "openai-completions": "openai-completions",
        "openai_completions": "openai-completions",
        "messages": "anthropic-messages",
        "anthropic": "anthropic-messages",
        "anthropic-messages": "anthropic-messages",
        "anthropic_messages": "anthropic-messages",
    }
    resolved = alias_map.get(normalized)
    if resolved is None:
        supported = "、".join(SUPPORTED_API_MODES)
        raise ValueError(f"不支持的模型协议：{value}。仅支持：{supported}")
    return resolved
