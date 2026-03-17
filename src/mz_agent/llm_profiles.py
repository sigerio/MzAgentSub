"""MzAgent LLM 配置方案存储。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROFILE_STORAGE_RELATIVE_PATH = Path(".mz_agent/llm_profiles.json")
ProfileProviderType = Literal["openai_native", "openai_compatible_proxy"]


class LLMProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    provider_type: ProfileProviderType
    display_name: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    api_mode: str = "responses"
    timeout: int = Field(default=60, ge=1)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)

    def is_configured(self) -> bool:
        if not self.default_model or not self.api_key:
            return False
        if self.provider_type == "openai_native":
            return True
        return bool(self.base_url)

    def resolved_display_name(self) -> str:
        return self.display_name or self.profile_name

    def masked_api_key(self) -> str | None:
        if not self.api_key:
            return None
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}***{self.api_key[-4:]}"


class LLMProfileStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_profile_name: str
    profiles: list[LLMProfile] = Field(default_factory=list)

    def profile_map(self) -> dict[str, LLMProfile]:
        return {profile.profile_name: profile for profile in self.profiles}

    def get(self, profile_name: str) -> LLMProfile | None:
        return self.profile_map().get(profile_name)

    def require(self, profile_name: str) -> LLMProfile:
        profile = self.get(profile_name)
        if profile is None:
            raise ValueError(f"未找到配置方案：{profile_name}")
        return profile

    def upsert(self, profile: LLMProfile) -> "LLMProfileStore":
        profile_map = self.profile_map()
        profile_map[profile.profile_name] = profile
        ordered_profiles = [
            profile_map[name]
            for name in sorted(profile_map.keys())
        ]
        default_profile_name = self.default_profile_name or profile.profile_name
        if default_profile_name not in profile_map:
            default_profile_name = profile.profile_name
        return LLMProfileStore(
            default_profile_name=default_profile_name,
            profiles=ordered_profiles,
        )

    def delete(self, profile_name: str) -> "LLMProfileStore":
        profile_map = self.profile_map()
        if profile_name not in profile_map:
            raise ValueError(f"未找到配置方案：{profile_name}")
        if len(profile_map) == 1:
            raise ValueError("至少需要保留一套配置方案。")
        profile_map.pop(profile_name)
        ordered_profiles = [
            profile_map[name]
            for name in sorted(profile_map.keys())
        ]
        default_profile_name = self.default_profile_name
        if default_profile_name == profile_name or default_profile_name not in profile_map:
            default_profile_name = ordered_profiles[0].profile_name
        return LLMProfileStore(
            default_profile_name=default_profile_name,
            profiles=ordered_profiles,
        )

    def activate(self, profile_name: str) -> "LLMProfileStore":
        self.require(profile_name)
        return LLMProfileStore(
            default_profile_name=profile_name,
            profiles=list(self.profiles),
        )


def load_profile_store(
    *,
    project_root: Path,
    env_values: dict[str, str] | None = None,
) -> LLMProfileStore:
    storage_path = project_root / PROFILE_STORAGE_RELATIVE_PATH
    if storage_path.exists():
        return LLMProfileStore.model_validate_json(storage_path.read_text(encoding="utf-8"))

    resolved_env = env_values if env_values is not None else _load_env_file(project_root / ".env")
    profile = build_legacy_default_profile(env_values=resolved_env)
    return LLMProfileStore(default_profile_name=profile.profile_name, profiles=[profile])


def save_profile_store(*, project_root: Path, store: LLMProfileStore) -> None:
    storage_path = project_root / PROFILE_STORAGE_RELATIVE_PATH
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(
        json.dumps(store.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_legacy_default_profile(*, env_values: dict[str, str]) -> LLMProfile:
    model_name = env_values.get("LLM_MODEL_ID") or None
    api_key = env_values.get("LLM_API_KEY") or None
    base_url = env_values.get("LLM_BASE_URL") or None
    timeout = _read_timeout(env_values)
    provider_type: ProfileProviderType = (
        "openai_compatible_proxy" if base_url else "openai_native"
    )
    return LLMProfile(
        profile_name="default",
        display_name="默认方案",
        provider_type=provider_type,
        default_model=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )


def _read_timeout(env_values: dict[str, str]) -> int:
    raw_timeout = env_values.get("LLM_TIMEOUT")
    if raw_timeout is None:
        return 60
    try:
        parsed = int(raw_timeout)
    except ValueError:
        return 60
    return parsed if parsed > 0 else 60


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip('"').strip("'")
    return values
