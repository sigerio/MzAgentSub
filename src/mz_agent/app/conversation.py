"""MzAgent Web/CLI 共用会话服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..capabilities import (
    CapabilityItem,
    CapabilityRegistry,
    CapabilityType,
    load_capability_registry,
    save_capability_registry,
)
from ..contracts.context import ContextSnapshot
from ..contracts.state import ReactStatus
from ..llm_profiles import LLMProfile, LLMProfileStore, load_profile_store, save_profile_store
from ..orchestration import FileBackedSTM, Pipeline, PipelineRoundResult
from .runtime import RuntimeOptions, build_runtime, render_round_result, run_single_round

ResultType = Literal["finish", "clarify", "tool", "mcp", "llm", "rag", "skill", "error", "unknown"]
StatusKey = Literal["idle", "needs_clarify", "completed", "failed"]


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    round_id: str | None = None


class SessionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status_key: StatusKey
    status_label: str
    can_submit: bool
    history_count: int
    active_profile_name: str | None = None
    result_profile_name: str | None = None
    result_type: ResultType | None = None
    result_text: str | None = None
    clarify_reason: str | None = None


class RoundSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    action_type: str
    target: str | None = None
    profile_name: str | None = None
    enabled_capabilities: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    enabled_mcp: list[str] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    rag_enabled: bool = False


class RoundRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_id: str
    goal: str
    action_type: str
    target: str | None = None
    profile_name: str | None = None
    enabled_capabilities: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    enabled_mcp: list[str] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    rag_enabled: bool = False
    retry_from_round_id: str | None = None


class RoundResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    round_id: str
    retry_from_round_id: str | None = None
    profile_name: str | None = None
    status: SessionStatus
    result_type: ResultType
    result_text: str
    history: list[ConversationMessage] = Field(default_factory=list)
    raw_result: dict[str, object]


class HistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    history: list[ConversationMessage] = Field(default_factory=list)


class ResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: SessionStatus
    history: list[ConversationMessage] = Field(default_factory=list)
    message: str


class CapabilityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_type: CapabilityType
    items: list[CapabilityItem] = Field(default_factory=list)


class CapabilityMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    capability_type: CapabilityType
    items: list[CapabilityItem] = Field(default_factory=list)


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    display_name: str | None = None
    provider_type: str
    default_model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    api_mode: str = "responses"
    timeout: int = Field(default=60, ge=1)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)

    def to_profile(self) -> LLMProfile:
        return LLMProfile(
            profile_name=self.profile_name,
            display_name=self.display_name,
            provider_type=self.provider_type,  # type: ignore[arg-type]
            default_model=self.default_model,
            api_key=self.api_key,
            base_url=self.base_url,
            api_mode=self.api_mode,
            timeout=self.timeout,
            extra_headers=dict(self.extra_headers),
            enabled_capabilities=list(self.enabled_capabilities),
        )


class ProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    display_name: str
    provider_type: str
    default_model: str | None = None
    api_key_masked: str | None = None
    base_url: str | None = None
    api_mode: str
    timeout: int
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)
    is_default: bool = False


class ProfileListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_profile_name: str
    active_profile_name: str
    profiles: list[ProfileView] = Field(default_factory=list)


class ProfileMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    profiles: ProfileListResponse


class ConversationService:
    def __init__(
        self,
        *,
        project_root: Path,
        options: RuntimeOptions | None = None,
        pipeline: Pipeline | None = None,
        stm: FileBackedSTM | None = None,
    ) -> None:
        self._project_root = project_root
        self._options = options or RuntimeOptions()
        if pipeline is not None and stm is not None:
            self._pipeline = pipeline
            self._stm = stm
        else:
            self._pipeline, self._stm = build_runtime(
                options=self._options,
                project_root=project_root,
            )

    @property
    def session_id(self) -> str:
        return self._options.session_id

    def ensure_session(self, *, session_id: str) -> None:
        if session_id != self.session_id:
            raise ValueError(f"未知会话：{session_id}")

    def submit_round(self, *, submission: RoundSubmission) -> RoundResponse:
        goal = submission.goal.strip()
        if not goal:
            raise ValueError("goal 不能为空。")
        active_profile_name = self._resolve_effective_profile_name(
            requested_profile_name=submission.profile_name
        )
        normalized = submission.model_copy(
            update={
                "goal": goal,
                "profile_name": active_profile_name,
            }
        )
        record = RoundRecord(
            round_id=_build_round_id(),
            goal=normalized.goal,
            action_type=normalized.action_type,
            target=normalized.target,
            profile_name=normalized.profile_name,
            enabled_capabilities=list(normalized.enabled_capabilities),
            enabled_tools=list(normalized.enabled_tools),
            enabled_mcp=list(normalized.enabled_mcp),
            enabled_skills=list(normalized.enabled_skills),
            rag_enabled=normalized.rag_enabled,
        )
        return self._execute_round_record(record=record)

    def retry_round(self, *, round_id: str) -> RoundResponse:
        round_records = self._read_round_records(snapshot=self._stm.latest_context_snapshot())
        target_index: int | None = None
        for index, record in enumerate(round_records):
            if record.round_id == round_id:
                target_index = index
                break
        if target_index is None:
            raise ValueError(f"未找到指定轮次：{round_id}")

        replay_records = list(round_records[:target_index])
        retried_record = round_records[target_index].model_copy(
            update={
                "round_id": _build_round_id(),
                "retry_from_round_id": round_id,
            }
        )
        replay_records.append(retried_record)
        self._stm.replace_context_snapshot(snapshot=ContextSnapshot(current_plan=None))

        response: RoundResponse | None = None
        for record in replay_records:
            response = self._execute_round_record(record=record)
        if response is None:
            raise ValueError("重试失败：未生成任何轮次结果。")
        return response

    def get_history(self) -> HistoryResponse:
        return HistoryResponse(
            session_id=self.session_id,
            history=read_conversation_history(snapshot=self._stm.latest_context_snapshot()),
        )

    def get_status(self) -> SessionStatus:
        snapshot = self._stm.latest_context_snapshot()
        return build_session_status(
            session_id=self.session_id,
            snapshot=snapshot,
            active_profile_name=self._load_profile_store().default_profile_name,
            result_profile_name=derive_result_profile_name(snapshot=snapshot),
            result_type=derive_result_type_from_snapshot(snapshot=snapshot),
            result_text=derive_result_text_from_snapshot(snapshot=snapshot),
        )

    def reset_session(self) -> ResetResponse:
        self._stm.replace_context_snapshot(snapshot=ContextSnapshot(current_plan=None))
        status = self.get_status()
        return ResetResponse(
            session_id=self.session_id,
            status=status,
            history=[],
            message="当前会话已重置。",
        )

    def list_profiles(self) -> ProfileListResponse:
        store = self._load_profile_store()
        return self._build_profile_list_response(store=store)

    def list_capabilities(self, *, capability_type: CapabilityType) -> CapabilityListResponse:
        registry = self._load_capability_registry()
        return CapabilityListResponse(
            capability_type=capability_type,
            items=registry.items_for(capability_type),
        )

    def save_capability(
        self,
        *,
        capability_type: CapabilityType,
        item: CapabilityItem,
    ) -> CapabilityMutationResponse:
        registry = self._load_capability_registry().upsert(
            capability_type=capability_type,
            item=item,
        )
        save_capability_registry(project_root=self._project_root, registry=registry)
        return CapabilityMutationResponse(
            message=f"已保存能力项：{item.name}",
            capability_type=capability_type,
            items=registry.items_for(capability_type),
        )

    def delete_capability(
        self,
        *,
        capability_type: CapabilityType,
        name: str,
    ) -> CapabilityMutationResponse:
        registry = self._load_capability_registry().delete(
            capability_type=capability_type,
            name=name,
        )
        save_capability_registry(project_root=self._project_root, registry=registry)
        return CapabilityMutationResponse(
            message=f"已删除能力项：{name}",
            capability_type=capability_type,
            items=registry.items_for(capability_type),
        )

    def toggle_capability(
        self,
        *,
        capability_type: CapabilityType,
        name: str,
    ) -> CapabilityMutationResponse:
        registry, updated = self._load_capability_registry().toggle(
            capability_type=capability_type,
            name=name,
        )
        save_capability_registry(project_root=self._project_root, registry=registry)
        state_label = "启用" if updated.enabled else "禁用"
        return CapabilityMutationResponse(
            message=f"已{state_label}能力项：{name}",
            capability_type=capability_type,
            items=registry.items_for(capability_type),
        )

    def save_profile(self, *, payload: ProfilePayload) -> ProfileMutationResponse:
        if payload.base_url and not payload.base_url.startswith(("https://", "http://")):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头。")

        store = self._load_profile_store()
        existing = store.get(payload.profile_name)
        profile = payload.to_profile()
        if existing is not None and not profile.api_key:
            profile = profile.model_copy(update={"api_key": existing.api_key})
        store = store.upsert(profile)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message=f"已保存配置方案：{profile.profile_name}",
            profiles=self._build_profile_list_response(store=store),
        )

    def delete_profile(self, *, profile_name: str) -> ProfileMutationResponse:
        store = self._load_profile_store().delete(profile_name)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message=f"已删除配置方案：{profile_name}",
            profiles=self._build_profile_list_response(store=store),
        )

    def activate_profile(self, *, profile_name: str) -> ProfileMutationResponse:
        store = self._load_profile_store().activate(profile_name)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message=f"已切换当前配置方案：{profile_name}",
            profiles=self._build_profile_list_response(store=store),
        )

    def _load_profile_store(self) -> LLMProfileStore:
        return load_profile_store(project_root=self._project_root)

    def _load_capability_registry(self) -> CapabilityRegistry:
        return load_capability_registry(project_root=self._project_root)

    def _resolve_effective_profile_name(self, *, requested_profile_name: str | None) -> str:
        store = self._load_profile_store()
        if requested_profile_name:
            store.require(requested_profile_name)
            return requested_profile_name
        return store.default_profile_name

    def _build_profile_list_response(self, *, store: LLMProfileStore) -> ProfileListResponse:
        return ProfileListResponse(
            default_profile_name=store.default_profile_name,
            active_profile_name=store.default_profile_name,
            profiles=[
                ProfileView(
                    profile_name=profile.profile_name,
                    display_name=profile.resolved_display_name(),
                    provider_type=profile.provider_type,
                    default_model=profile.default_model,
                    api_key_masked=profile.masked_api_key(),
                    base_url=profile.base_url,
                    api_mode=profile.api_mode,
                    timeout=profile.timeout,
                    extra_headers=dict(profile.extra_headers),
                    enabled_capabilities=list(profile.enabled_capabilities),
                    is_default=profile.profile_name == store.default_profile_name,
                )
                for profile in store.profiles
            ],
        )

    def _execute_round_record(self, *, record: RoundRecord) -> RoundResponse:
        result = run_single_round(
            options=self._options,
            pipeline=self._pipeline,
            stm=self._stm,
            goal=record.goal,
            action_type=record.action_type,
            target=record.target,
            profile_name=record.profile_name,
            enabled_capabilities=record.enabled_capabilities,
            enabled_tools=record.enabled_tools,
            enabled_mcp=record.enabled_mcp,
            enabled_skills=record.enabled_skills,
            rag_enabled=record.rag_enabled,
            round_id=record.round_id,
        )
        snapshot = self._append_round_record(
            snapshot=self._stm.latest_context_snapshot(),
            record=record,
        )
        history = read_conversation_history(snapshot=snapshot)
        result_type = derive_result_type(result=result)
        result_text = render_round_result(result=result)
        status = build_session_status(
            session_id=self.session_id,
            snapshot=snapshot,
            active_profile_name=self._load_profile_store().default_profile_name,
            result_profile_name=derive_result_profile_name(snapshot=snapshot),
            result_type=result_type,
            result_text=result_text,
        )
        return RoundResponse(
            session_id=self.session_id,
            round_id=record.round_id,
            retry_from_round_id=record.retry_from_round_id,
            profile_name=record.profile_name,
            status=status,
            result_type=result_type,
            result_text=result_text,
            history=history,
            raw_result=result.model_dump(mode="json"),
        )

    def _append_round_record(
        self,
        *,
        snapshot: ContextSnapshot,
        record: RoundRecord,
    ) -> ContextSnapshot:
        round_records = self._read_round_records(snapshot=snapshot)
        round_records.append(record)
        stm_state = dict(snapshot.stm)
        stm_state["round_records"] = [
            round_record.model_dump(mode="json")
            for round_record in round_records
        ]
        updated_snapshot = snapshot.model_copy(update={"stm": stm_state})
        return self._stm.replace_context_snapshot(snapshot=updated_snapshot)

    @staticmethod
    def _read_round_records(*, snapshot: ContextSnapshot) -> list[RoundRecord]:
        raw_records = snapshot.stm.get("round_records", [])
        if not isinstance(raw_records, list):
            return []
        records: list[RoundRecord] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            records.append(RoundRecord.model_validate(item))
        return records


def read_conversation_history(*, snapshot: ContextSnapshot) -> list[ConversationMessage]:
    raw_history = snapshot.perception.get("conversation_messages", [])
    history: list[ConversationMessage] = []
    if not isinstance(raw_history, list):
        return history
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if isinstance(role, str) and isinstance(content, str):
            round_id = item.get("round_id")
            history.append(
                ConversationMessage(
                    role=role,
                    content=content,
                    round_id=round_id if isinstance(round_id, str) else None,
                )
            )
    return history


def derive_result_type(*, result: PipelineRoundResult) -> ResultType:
    next_action = result.react_result.next_action
    if next_action is not None and next_action.action_type == "clarify":
        return "clarify"

    if result.react_result.react_status is ReactStatus.FINISHED:
        return "finish"

    observation = result.observation or {}
    source = observation.get("source")
    if source in {"tool", "mcp", "llm", "rag", "skill"}:
        return source

    if result.react_result.react_status in {ReactStatus.BLOCKED, ReactStatus.DEGRADED}:
        return "error"

    return "unknown"


def derive_result_type_from_snapshot(*, snapshot: ContextSnapshot) -> ResultType | None:
    observation = snapshot.last_observation or {}
    source = observation.get("source")
    if source in {"tool", "mcp", "llm", "rag", "skill"}:
        return source
    if source == "answer":
        output_text = observation.get("output_text")
        if isinstance(output_text, str) and "请补充" in output_text:
            return "clarify"
        return "finish"

    react_status = snapshot.stm.get("last_react_status")
    if react_status in {ReactStatus.BLOCKED.value, ReactStatus.DEGRADED.value}:
        return "error"
    return None


def derive_result_text_from_snapshot(*, snapshot: ContextSnapshot) -> str | None:
    history = read_conversation_history(snapshot=snapshot)
    if history:
        return history[-1].content
    return None


def build_session_status(
    *,
    session_id: str,
    snapshot: ContextSnapshot,
    active_profile_name: str | None,
    result_profile_name: str | None,
    result_type: ResultType | None,
    result_text: str | None,
) -> SessionStatus:
    history = read_conversation_history(snapshot=snapshot)
    clarify_reason = snapshot.perception.get("clarify_reason")
    if not isinstance(clarify_reason, str):
        clarify_reason = None

    status_key: StatusKey
    if not history and snapshot.last_observation is None:
        status_key = "idle"
    elif result_type == "clarify" or bool(snapshot.perception.get("clarify_needed")):
        status_key = "needs_clarify"
    elif snapshot.stm.get("last_react_status") in {
        ReactStatus.BLOCKED.value,
        ReactStatus.DEGRADED.value,
    }:
        status_key = "failed"
    else:
        status_key = "completed"

    label_map = {
        "idle": "待输入",
        "needs_clarify": "需要澄清",
        "completed": "已完成",
        "failed": "执行失败",
    }
    return SessionStatus(
        session_id=session_id,
        status_key=status_key,
        status_label=label_map[status_key],
        can_submit=True,
        history_count=len(history),
        active_profile_name=active_profile_name,
        result_profile_name=result_profile_name,
        result_type=result_type,
        result_text=result_text,
        clarify_reason=clarify_reason,
    )


def derive_result_profile_name(*, snapshot: ContextSnapshot) -> str | None:
    observation = snapshot.last_observation or {}
    response = observation.get("response")
    if isinstance(response, dict):
        provider_trace = response.get("provider_trace")
        if isinstance(provider_trace, dict):
            profile_name = provider_trace.get("profile_name")
            if isinstance(profile_name, str) and profile_name:
                return profile_name
    return None


def _build_round_id() -> str:
    return f"round_{uuid4().hex[:10]}"
