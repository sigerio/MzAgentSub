"""MzAgent Web/CLI 共用会话服务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..adapters import LLMAdapter
from ..capabilities import (
    CapabilityItem,
    CapabilityRegistry,
    CapabilityType,
    load_capability_registry,
    save_capability_registry,
)
from ..contracts.action import AvailableAction, NextAction
from ..contracts.context import ContextSnapshot, ExecutionContext
from ..contracts.llm import LLMMessage, LLMRequest
from ..contracts.state import ReactStatus
from ..http_headers import build_default_http_headers
from ..llm_profiles import (
    DEFAULT_API_MODE,
    LLMConnection,
    LLMProfile,
    LLMProfileStore,
    load_profile_store,
    save_profile_store,
)
from ..orchestration import FileBackedSTM, Pipeline, PipelineRoundResult
from ..runtime.writeback import prepare_writeback_record
from .runtime import (
    RuntimeOptions,
    build_available_actions,
    build_pending_action_arguments,
    build_request_identifiers,
    build_runtime,
    extract_text_from_llm_response,
    render_round_result,
    run_single_round,
)

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


class AutoActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: Literal["llm", "tool", "mcp", "skill", "rag", "finish", "clarify"] = "llm"
    target: str | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    respond_with_llm: bool = True
    expect_user_followup: bool = False
    reason: str = ""


class PendingExternalInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["mcp"]
    target: str
    prompt: str
    resume_strategy: str = "llm_route"
    last_observation: dict[str, object] = Field(default_factory=dict)


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


class ConnectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_key: str | None = None
    timeout: int = Field(default=60, ge=1)


class ConnectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key_masked: str | None = None
    timeout: int = Field(default=60, ge=1)
    is_configured: bool = False


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    api_mode: str = DEFAULT_API_MODE
    profile_name: str | None = None
    display_name: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)

    def to_profile(self) -> LLMProfile:
        normalized_model_name = self.model_name.strip()
        profile_name = (self.profile_name or normalized_model_name).strip()
        display_name = (self.display_name or normalized_model_name).strip()
        return LLMProfile(
            profile_name=profile_name,
            display_name=display_name,
            model_name=normalized_model_name,
            api_mode=self.api_mode,
            extra_headers=dict(self.extra_headers),
            enabled_capabilities=list(self.enabled_capabilities),
        )


class ProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    display_name: str
    model_name: str
    api_mode: str = DEFAULT_API_MODE
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)
    is_active: bool = False


class ProfileListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: ConnectionView = Field(default_factory=ConnectionView)
    active_profile_name: str | None = None
    profiles: list[ProfileView] = Field(default_factory=list)


class ProfileMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    profiles: ProfileListResponse


class ModelDiscoverResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    models: list[str] = Field(default_factory=list)


class ProfileConnectionTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    ok: bool
    message: str
    error_code: str | None = None
    model: str | None = None
    api_mode: str = DEFAULT_API_MODE
    latency_ms: int = Field(default=0, ge=0)
    output_text: str | None = None


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
            active_profile_name=self._load_profile_store().resolve_active_profile_name(),
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

    def save_connection(self, *, payload: ConnectionPayload) -> ProfileMutationResponse:
        base_url = _normalize_base_url(payload.base_url)
        store = self._load_profile_store()
        existing_connection = store.connection or LLMConnection()
        api_key = (payload.api_key or "").strip() or existing_connection.api_key
        if not api_key:
            raise ValueError("请先填写 NewAPI API Key。")

        connection = LLMConnection(
            base_url=base_url,
            api_key=api_key,
            timeout=payload.timeout,
        )
        store = store.set_connection(connection)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message="已保存 NewAPI 连接配置。",
            profiles=self._build_profile_list_response(store=store),
        )

    def discover_connection_models(self) -> ModelDiscoverResponse:
        store = self._load_profile_store()
        connection = self._require_connection(store=store)
        models = self._fetch_connection_model_names(connection=connection)
        if not models:
            return ModelDiscoverResponse(
                message="当前站点未返回可用模型。",
                models=[],
            )
        return ModelDiscoverResponse(
            message=f"已获取 {len(models)} 个可用模型。",
            models=models,
        )

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
        store = self._load_profile_store()
        self._require_connection(store=store)
        profile = payload.to_profile()
        if not profile.model_name:
            raise ValueError("请先选择要添加的模型。")

        existing = store.get(profile.profile_name)
        store = store.upsert(profile)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message=f"已{'更新' if existing is not None else '添加'}模型：{profile.profile_name}",
            profiles=self._build_profile_list_response(store=store),
        )

    def delete_profile(self, *, profile_name: str) -> ProfileMutationResponse:
        store = self._load_profile_store().delete(profile_name)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message=f"已删除模型：{profile_name}",
            profiles=self._build_profile_list_response(store=store),
        )

    def activate_profile(self, *, profile_name: str) -> ProfileMutationResponse:
        store = self._load_profile_store().activate(profile_name)
        save_profile_store(project_root=self._project_root, store=store)
        return ProfileMutationResponse(
            message=f"已启用模型：{profile_name}",
            profiles=self._build_profile_list_response(store=store),
        )

    def test_profile_connection(self, *, profile_name: str) -> ProfileConnectionTestResponse:
        store = self._load_profile_store()
        profile = store.require(profile_name)
        connection = store.connection
        if connection is None or not connection.api_key:
            return ProfileConnectionTestResponse(
                profile_name=profile_name,
                ok=False,
                message="当前未配置 NewAPI API Key，请先保存连接配置。",
                error_code="missing_api_key",
                model=profile.model_name,
                api_mode=profile.api_mode,
            )
        if not connection.base_url:
            return ProfileConnectionTestResponse(
                profile_name=profile_name,
                ok=False,
                message="当前未配置 NewAPI base_url，请先保存连接配置。",
                error_code="missing_base_url",
                model=profile.model_name,
                api_mode=profile.api_mode,
            )

        timeout_ms = min(connection.timeout, 15) * 1000
        adapter = LLMAdapter(project_root=self._project_root, live_mode=True)

        try:
            response = adapter.test_connection(
                profile_name=profile_name,
                timeout_ms=timeout_ms,
            )
        except ModuleNotFoundError:
            return ProfileConnectionTestResponse(
                profile_name=profile_name,
                ok=False,
                message="当前环境未安装 openai 依赖，无法执行连接测试。",
                error_code="missing_dependency",
                model=profile.model_name,
                api_mode=profile.api_mode,
            )
        except Exception as exc:
            return self._build_profile_connection_failure_response(
                profile=profile,
                exc=exc,
            )

        output_text = "\n".join(
            block.content
            for block in response.content_blocks
            if block.type == "text" and block.content
        ).strip() or None
        return ProfileConnectionTestResponse(
            profile_name=profile_name,
            ok=True,
            message=f"连接测试成功：{profile_name}",
            model=response.provider_trace.model if response.provider_trace else profile.model_name,
            api_mode=response.provider_trace.api_mode if response.provider_trace else profile.api_mode,
            latency_ms=response.latency_ms,
            output_text=output_text,
        )

    def _load_profile_store(self) -> LLMProfileStore:
        return load_profile_store(project_root=self._project_root)

    def _load_capability_registry(self) -> CapabilityRegistry:
        return load_capability_registry(project_root=self._project_root)

    @staticmethod
    def _require_connection(*, store: LLMProfileStore) -> LLMConnection:
        connection = store.connection
        if connection is None or not connection.is_configured():
            raise ValueError("当前未配置 NewAPI 连接，请先填写 base_url 与 api_key。")
        return connection

    @staticmethod
    def _build_profile_connection_failure_response(
        *,
        profile: LLMProfile,
        exc: Exception,
    ) -> ProfileConnectionTestResponse:
        try:
            import openai
        except ModuleNotFoundError:
            openai = None  # type: ignore[assignment]

        from ..adapters.llm import ProviderRequestError

        message = f"连接测试失败：{exc}"
        error_code = "unknown_error"

        if isinstance(exc, ProviderRequestError):
            if exc.status_code == 400:
                message = "请求参数无效，请检查当前方案的模型名、接口模式或代理兼容性。"
                error_code = "bad_request"
            elif exc.status_code == 401:
                message = "认证失败，请检查当前方案的 API Key 是否正确。"
                error_code = "authentication_failed"
            elif exc.status_code == 403:
                message = "当前方案无权限访问该模型或接口。"
                error_code = "permission_denied"
            elif exc.status_code == 404:
                message = "未找到目标模型或接口地址，请检查模型名与 base_url。"
                error_code = "not_found"
            elif exc.status_code == 429:
                message = "请求已被限流，请稍后再试。"
                error_code = "rate_limited"
            elif exc.status_code is not None:
                message = f"接口返回异常状态：{exc.status_code}"
                error_code = "api_status_error"
            else:
                message = str(exc)
                error_code = "connection_failed"
        elif openai is not None:
            if isinstance(exc, openai.APITimeoutError):
                message = "连接测试超时，请检查网络、接口地址或服务端响应速度。"
                error_code = "timeout"
            elif isinstance(exc, openai.AuthenticationError):
                message = "认证失败，请检查当前方案的 API Key 是否正确。"
                error_code = "authentication_failed"
            elif isinstance(exc, openai.PermissionDeniedError):
                message = "当前方案无权限访问该模型或接口。"
                error_code = "permission_denied"
            elif isinstance(exc, openai.NotFoundError):
                message = "未找到目标模型或接口地址，请检查模型名与 base_url。"
                error_code = "not_found"
            elif isinstance(exc, openai.RateLimitError):
                message = "请求已被限流，请稍后再试。"
                error_code = "rate_limited"
            elif isinstance(exc, openai.BadRequestError):
                message = "请求参数无效，请检查当前方案的模型名、接口模式或代理兼容性。"
                error_code = "bad_request"
            elif isinstance(exc, openai.InternalServerError):
                message = "目标服务内部错误，请稍后再试。"
                error_code = "internal_server_error"
            elif isinstance(exc, openai.APIConnectionError):
                message = "连接失败，请检查网络连通性、接口地址和代理服务状态。"
                error_code = "connection_failed"
            elif isinstance(exc, openai.APIStatusError):
                status_code = getattr(exc, "status_code", None)
                message = f"接口返回异常状态：{status_code}"
                error_code = "api_status_error"

        return ProfileConnectionTestResponse(
            profile_name=profile.profile_name,
            ok=False,
            message=message,
            error_code=error_code,
            model=profile.model_name,
            api_mode=profile.api_mode,
        )

    def _resolve_effective_profile_name(self, *, requested_profile_name: str | None) -> str:
        store = self._load_profile_store()
        if requested_profile_name:
            store.require(requested_profile_name)
            return requested_profile_name
        active_profile_name = store.resolve_active_profile_name()
        if not active_profile_name:
            raise ValueError("当前无配置方案，请先配置连接并添加模型。")
        return active_profile_name

    def _build_profile_list_response(self, *, store: LLMProfileStore) -> ProfileListResponse:
        return ProfileListResponse(
            connection=ConnectionView(
                base_url=store.connection.base_url if store.connection else None,
                api_key_masked=store.connection.masked_api_key() if store.connection else None,
                timeout=store.connection.timeout if store.connection else 60,
                is_configured=store.connection.is_configured() if store.connection else False,
            ),
            active_profile_name=store.resolve_active_profile_name(),
            profiles=[
                ProfileView(
                    profile_name=profile.profile_name,
                    display_name=profile.resolved_display_name(),
                    model_name=profile.model_name,
                    api_mode=profile.api_mode,
                    extra_headers=dict(profile.extra_headers),
                    enabled_capabilities=list(profile.enabled_capabilities),
                    is_active=profile.profile_name == store.resolve_active_profile_name(),
                )
                for profile in store.profiles
            ],
        )

    @staticmethod
    def _fetch_connection_model_names(*, connection: LLMConnection) -> list[str]:
        request_url = f"{connection.base_url.rstrip('/')}/models"
        last_http_error: ValueError | None = None

        for headers in _build_model_discovery_headers(api_key=connection.api_key):
            request = urllib_request.Request(
                request_url,
                headers=headers,
                method="GET",
            )
            try:
                with urllib_request.urlopen(request, timeout=min(connection.timeout, 20)) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return _extract_model_names_from_payload(payload)
            except urllib_error.HTTPError as exc:
                last_http_error = ValueError(f"获取模型失败：{_read_http_error_message(exc)}")
                if exc.code not in {401, 403}:
                    raise last_http_error from exc
            except urllib_error.URLError as exc:
                raise ValueError(f"获取模型失败：{exc.reason}") from exc

        if last_http_error is not None:
            raise last_http_error
        return []

    def _execute_round_record(self, *, record: RoundRecord) -> RoundResponse:
        if record.action_type == "auto":
            return self._execute_auto_round_record(record=record)
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
            active_profile_name=self._load_profile_store().resolve_active_profile_name(),
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

    def _execute_auto_round_record(
        self,
        *,
        record: RoundRecord,
    ) -> RoundResponse:
        snapshot = self._stm.latest_context_snapshot()
        available_actions = build_available_actions(
            pipeline=self._pipeline,
            action_type="auto",
            target=None,
            enabled_capabilities=record.enabled_capabilities,
            enabled_tools=record.enabled_tools,
            enabled_mcp=record.enabled_mcp,
            enabled_skills=record.enabled_skills,
            rag_enabled=record.rag_enabled,
        )
        route_decision = self._decide_auto_action(
            record=record,
            snapshot=snapshot,
            available_actions=available_actions,
        )
        if route_decision.action_type in {"llm", "finish", "clarify"}:
            snapshot = self._with_pending_external_interaction(
                snapshot=snapshot,
                pending=None,
            )
            return self._complete_round_with_llm(
                record=record,
                snapshot=snapshot,
                intermediate_observations=[],
                route_decision=route_decision,
            )

        observation = self._execute_auto_action(
            record=record,
            decision=route_decision,
        )
        intermediate_observations = [observation]
        if route_decision.expect_user_followup and observation.get("source") == "mcp":
            pending = self._build_pending_external_interaction(
                decision=route_decision,
                observation=observation,
            )
            if pending is not None:
                snapshot = self._with_pending_external_interaction(
                    snapshot=snapshot,
                    pending=pending,
                )
                return self._complete_round_with_observation(
                    record=record,
                    snapshot=snapshot,
                    observation=observation,
                    intermediate_observations=intermediate_observations,
                    route_decision=route_decision,
                )

        if not route_decision.respond_with_llm:
            snapshot = self._with_pending_external_interaction(
                snapshot=snapshot,
                pending=None,
            )
            return self._complete_round_with_observation(
                record=record,
                snapshot=snapshot,
                observation=observation,
                intermediate_observations=intermediate_observations,
                route_decision=route_decision,
            )

        snapshot = self._with_pending_external_interaction(
            snapshot=snapshot,
            pending=None,
        )
        return self._complete_round_with_llm(
            record=record,
            snapshot=snapshot,
            intermediate_observations=intermediate_observations,
            route_decision=route_decision,
        )

    def _complete_round_with_llm(
        self,
        *,
        record: RoundRecord,
        snapshot: ContextSnapshot,
        intermediate_observations: list[dict[str, object]],
        route_decision: AutoActionDecision | None = None,
    ) -> RoundResponse:
        prepared_snapshot = self._prepare_snapshot_for_round_response(
            snapshot=snapshot,
            goal=record.goal,
            round_id=record.round_id,
        )
        pending_external_interaction = self._read_pending_external_interaction(
            snapshot=prepared_snapshot
        )
        history_messages = [
            LLMMessage(
                role=message.role if message.role in {"system", "user", "assistant", "tool"} else "assistant",
                content=message.content,
            )
            for message in read_conversation_history(snapshot=prepared_snapshot)
        ]
        llm_request = LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=_build_llm_completion_instruction(
                        goal=record.goal,
                        intermediate_observations=intermediate_observations,
                        pending_external_interaction=(
                            pending_external_interaction.model_dump(mode="json")
                            if pending_external_interaction is not None
                            else None
                        ),
                    ),
                ),
                *history_messages,
                LLMMessage(role="user", content=record.goal),
            ],
            model_policy="quality",
            profile_name=record.profile_name,
        )
        request_id, trace_id = build_request_identifiers(
            request_prefix=self._options.request_prefix,
            trace_prefix=self._options.trace_prefix,
            action_type="llm",
        )
        completion_trace_id = f"{trace_id}.completion"
        llm_response = self._pipeline.adapters.llm.respond(
            request=llm_request,
            execution_context=ExecutionContext(
                request_id=request_id,
                session_id=self.session_id,
                plan_id=None,
                trace_id=completion_trace_id,
                source="react",
            ),
        )
        self._stm.replace_context_snapshot(snapshot=prepared_snapshot)
        snapshot = self._stm.apply_writeback(
            record=prepare_writeback_record(
                stage="post_action",
                execution_context=ExecutionContext(
                    request_id=request_id,
                    session_id=self.session_id,
                    plan_id=None,
                    trace_id=completion_trace_id,
                    source="react",
                ),
                react_status=ReactStatus.RUNNING,
                current_step=None,
                observation={
                    "source": "llm",
                    "response": llm_response.model_dump(mode="json"),
                },
                metadata={
                    "guardrails_decision": "allow",
                    "llm_completion_enforced": True,
                    "intermediate_sources": [
                        str(item.get("source"))
                        for item in intermediate_observations
                        if isinstance(item.get("source"), str)
                    ],
                },
            )
        )
        snapshot = self._append_round_record(snapshot=snapshot, record=record)
        history = read_conversation_history(snapshot=snapshot)
        result_text = derive_result_text_from_snapshot(snapshot=snapshot) or ""
        status = build_session_status(
            session_id=self.session_id,
            snapshot=snapshot,
            active_profile_name=self._load_profile_store().resolve_active_profile_name(),
            result_profile_name=derive_result_profile_name(snapshot=snapshot),
            result_type="llm",
            result_text=result_text,
        )
        return RoundResponse(
            session_id=self.session_id,
            round_id=record.round_id,
            retry_from_round_id=record.retry_from_round_id,
            profile_name=record.profile_name,
            status=status,
            result_type="llm",
            result_text=result_text,
            history=history,
            raw_result={
                "llm_completion_enforced": True,
                "intermediate_observations": intermediate_observations,
                "final_observation": snapshot.last_observation or {},
                "route_decision": route_decision.model_dump(mode="json") if route_decision is not None else {},
                "pending_external_interaction": (
                    pending_external_interaction.model_dump(mode="json")
                    if pending_external_interaction is not None
                    else None
                ),
            },
        )

    def _complete_round_with_observation(
        self,
        *,
        record: RoundRecord,
        snapshot: ContextSnapshot,
        observation: dict[str, object],
        intermediate_observations: list[dict[str, object]],
        route_decision: AutoActionDecision,
    ) -> RoundResponse:
        prepared_snapshot = self._prepare_snapshot_for_round_response(
            snapshot=snapshot,
            goal=record.goal,
            round_id=record.round_id,
        )
        request_id, trace_id = build_request_identifiers(
            request_prefix=self._options.request_prefix,
            trace_prefix=self._options.trace_prefix,
            action_type=str(observation.get("source", route_decision.action_type)),
        )
        self._stm.replace_context_snapshot(snapshot=prepared_snapshot)
        snapshot = self._stm.apply_writeback(
            record=prepare_writeback_record(
                stage="post_action",
                execution_context=ExecutionContext(
                    request_id=request_id,
                    session_id=self.session_id,
                    plan_id=None,
                    trace_id=f"{trace_id}.pending",
                    source="react",
                ),
                react_status=ReactStatus.RUNNING,
                current_step=None,
                observation=observation,
                metadata={
                    "guardrails_decision": "allow",
                    "llm_completion_enforced": False,
                },
            )
        )
        snapshot = self._append_round_record(snapshot=snapshot, record=record)
        history = read_conversation_history(snapshot=snapshot)
        result_type = str(observation.get("source", "unknown"))
        result_text = derive_result_text_from_snapshot(snapshot=snapshot) or ""
        pending_external_interaction = self._read_pending_external_interaction(snapshot=snapshot)
        status = build_session_status(
            session_id=self.session_id,
            snapshot=snapshot,
            active_profile_name=self._load_profile_store().resolve_active_profile_name(),
            result_profile_name=derive_result_profile_name(snapshot=snapshot),
            result_type=result_type if result_type in {"tool", "mcp", "llm", "rag", "skill"} else "unknown",
            result_text=result_text,
        )
        return RoundResponse(
            session_id=self.session_id,
            round_id=record.round_id,
            retry_from_round_id=record.retry_from_round_id,
            profile_name=record.profile_name,
            status=status,
            result_type=result_type if result_type in {"tool", "mcp", "llm", "rag", "skill"} else "unknown",
            result_text=result_text,
            history=history,
            raw_result={
                "llm_completion_enforced": False,
                "intermediate_observations": intermediate_observations,
                "final_observation": observation,
                "route_decision": route_decision.model_dump(mode="json"),
                "pending_external_interaction": (
                    pending_external_interaction.model_dump(mode="json")
                    if pending_external_interaction is not None
                    else None
                ),
            },
        )

    def _prepare_snapshot_for_round_response(
        self,
        *,
        snapshot: ContextSnapshot,
        goal: str,
        round_id: str,
    ) -> ContextSnapshot:
        perception = dict(snapshot.perception)
        perception["pending_user_message"] = goal
        perception["pending_round_id"] = round_id
        return snapshot.model_copy(update={"perception": perception})

    def _decide_auto_action(
        self,
        *,
        record: RoundRecord,
        available_actions: list[AvailableAction],
        snapshot: ContextSnapshot,
    ) -> AutoActionDecision:
        candidate_actions = [
            action
            for action in available_actions
            if action.availability == "available" and action.action_type not in {"llm", "clarify", "finish"}
        ]
        if not candidate_actions:
            return AutoActionDecision(action_type="llm", respond_with_llm=True)

        pending_external_interaction = self._read_pending_external_interaction(snapshot=snapshot)
        history_messages = [
            LLMMessage(
                role=message.role if message.role in {"system", "user", "assistant", "tool"} else "assistant",
                content=message.content,
            )
            for message in read_conversation_history(snapshot=snapshot)
        ]
        llm_request = LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=_build_auto_route_instruction(
                        available_actions=candidate_actions,
                        pending_external_interaction=(
                            pending_external_interaction.model_dump(mode="json")
                            if pending_external_interaction is not None
                            else None
                        ),
                    ),
                ),
                *history_messages,
                LLMMessage(role="user", content=record.goal),
            ],
            model_policy="quality",
            profile_name=record.profile_name,
        )
        request_id, trace_id = build_request_identifiers(
            request_prefix=self._options.request_prefix,
            trace_prefix=self._options.trace_prefix,
            action_type="llm",
        )
        llm_response = self._pipeline.adapters.llm.respond(
            request=llm_request,
            execution_context=ExecutionContext(
                request_id=request_id,
                session_id=self.session_id,
                plan_id=None,
                trace_id=f"{trace_id}.route",
                source="react",
            ),
        )
        decision = _parse_auto_action_decision(
            text=extract_text_from_llm_response(
                response=llm_response.model_dump(mode="json")
            ),
            available_actions=candidate_actions,
            pending_external_interaction=pending_external_interaction,
        )
        return decision or AutoActionDecision(action_type="llm", respond_with_llm=True)

    def _execute_auto_action(
        self,
        *,
        record: RoundRecord,
        decision: AutoActionDecision,
    ) -> dict[str, object]:
        arguments = dict(decision.arguments)
        if not arguments:
            arguments = build_pending_action_arguments(
                action_type=decision.action_type,
                target=decision.target,
                goal=record.goal,
                profile_name=record.profile_name,
            ) or {}
        next_action = _build_routed_next_action(
            goal=record.goal,
            profile_name=record.profile_name,
            action_type=decision.action_type,
            target=decision.target,
            arguments=arguments,
        )
        request_id, trace_id = build_request_identifiers(
            request_prefix=self._options.request_prefix,
            trace_prefix=self._options.trace_prefix,
            action_type=decision.action_type,
        )
        try:
            return self._pipeline.adapters.dispatch(
                action=next_action,
                execution_context=ExecutionContext(
                    request_id=request_id,
                    session_id=self.session_id,
                    plan_id=None,
                    trace_id=f"{trace_id}.chain",
                    source="react",
                ),
            )
        except Exception as exc:
            return {
                "source": decision.action_type,
                "error": {
                    "message": str(exc),
                    "target": decision.target,
                },
            }

    @staticmethod
    def _build_pending_external_interaction(
        *,
        decision: AutoActionDecision,
        observation: dict[str, object],
    ) -> PendingExternalInteraction | None:
        result = observation.get("result")
        if not isinstance(result, dict):
            return None
        text = result.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        if not decision.target:
            return None
        return PendingExternalInteraction(
            source="mcp",
            target=decision.target,
            prompt=text.strip(),
            last_observation=observation,
        )

    @staticmethod
    def _read_pending_external_interaction(
        *,
        snapshot: ContextSnapshot,
    ) -> PendingExternalInteraction | None:
        raw_pending = snapshot.perception.get("pending_external_interaction")
        if not isinstance(raw_pending, dict):
            return None
        try:
            return PendingExternalInteraction.model_validate(raw_pending)
        except Exception:
            return None

    @staticmethod
    def _with_pending_external_interaction(
        *,
        snapshot: ContextSnapshot,
        pending: PendingExternalInteraction | None,
    ) -> ContextSnapshot:
        perception = dict(snapshot.perception)
        if pending is None:
            perception.pop("pending_external_interaction", None)
        else:
            perception["pending_external_interaction"] = pending.model_dump(mode="json")
        return snapshot.model_copy(update={"perception": perception})

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


def _normalize_base_url(raw_base_url: str) -> str:
    normalized = raw_base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("请先填写 NewAPI base_url。")
    if not normalized.startswith(("https://", "http://")):
        raise ValueError("base_url 必须以 http:// 或 https:// 开头。")
    return normalized


def _read_http_error_message(exc: urllib_error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        payload = None
    if isinstance(payload, dict):
        error_info = payload.get("error")
        if isinstance(error_info, dict):
            message = error_info.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return f"接口返回异常状态：{exc.code}"


def _build_model_discovery_headers(*, api_key: str) -> list[dict[str, str]]:
    normalized_api_key = api_key.strip()
    base_headers = {
        "Accept": "application/json",
        **build_default_http_headers(),
    }
    if not normalized_api_key:
        return [base_headers]
    return [
        {
            **base_headers,
            "Authorization": f"Bearer {normalized_api_key}",
            "x-api-key": normalized_api_key,
        },
        {
            **base_headers,
            "Authorization": f"Bearer {normalized_api_key}",
        },
    ]


def _build_llm_completion_instruction(
    *,
    goal: str,
    intermediate_observations: list[dict[str, object]],
    pending_external_interaction: dict[str, object] | None = None,
) -> str:
    summary_lines = [
        json.dumps(observation, ensure_ascii=False)
        for observation in intermediate_observations
    ]
    summary = "\n".join(summary_lines) if summary_lines else "无可用中间结果。"
    pending_summary = (
        json.dumps(pending_external_interaction, ensure_ascii=False)
        if pending_external_interaction is not None
        else "无待续外部交互。"
    )
    return "\n".join(
        [
            "你是 MzAgent 的最终答复层。",
            "当前轮次已经执行了若干中间编排节点，你必须继续面向用户给出最终答复。",
            "任一中间节点失败、为空、未命中，都不应阻断后续推理和最终答复。",
            "不要停留在工具结果、技能元数据或内部流程描述上。",
            "如果中间结果不足以完整完成任务，也要明确说明不足，并基于已有信息继续尽可能回答用户。",
            f"用户原始输入：{goal}",
            f"中间执行结果：{summary}",
            f"待续外部交互：{pending_summary}",
        ]
    )


def _build_auto_route_instruction(
    *,
    available_actions: list[AvailableAction],
    pending_external_interaction: dict[str, object] | None,
) -> str:
    available_payload = [
        {
            "action_type": action.action_type,
            "targets": list(action.targets),
        }
        for action in available_actions
    ]
    pending_summary = (
        json.dumps(pending_external_interaction, ensure_ascii=False)
        if pending_external_interaction is not None
        else "无"
    )
    return "\n".join(
        [
            "你是 MzAgent 的自动编排路由器。",
            "你只负责判断本轮是否需要调用外部能力，不负责直接回答用户问题。",
            "普通自然语言默认先交给 LLM，不要因为用户提到了某个服务名就直接调用 MCP。",
            "只有当外部能力明显更合适时，才选择 tool/mcp/skill/rag。",
            "如果存在待续外部交互，也必须先综合当前用户输入再决定是否继续同一个外部交互。",
            "你必须只输出一个 JSON 对象，不要输出解释。",
            "JSON 字段固定为：action_type、target、arguments、respond_with_llm、expect_user_followup、reason。",
            "其中：",
            "- action_type 只允许是 llm/tool/mcp/skill/rag",
            "- target 在需要外部能力时填写，否则为 null",
            "- arguments 为对象；若选择 mcp 且目标需要 message，请直接生成合适的 message，不要机械照抄服务名",
            "- respond_with_llm 表示执行完外部能力后是否继续回到 LLM",
            "- expect_user_followup 表示外部能力这一步主要是向用户继续提问或收集信息",
            f"当前可用动作：{json.dumps(available_payload, ensure_ascii=False)}",
            f"当前待续外部交互：{pending_summary}",
        ]
    )


def _parse_auto_action_decision(
    *,
    text: str,
    available_actions: list[AvailableAction],
    pending_external_interaction: PendingExternalInteraction | None,
) -> AutoActionDecision | None:
    payload = _extract_json_object(text=text)
    if payload is None:
        return None
    try:
        decision = AutoActionDecision.model_validate(payload)
    except Exception:
        return None

    allowed_targets = {
        action.action_type: list(action.targets)
        for action in available_actions
    }
    if decision.action_type == "llm":
        return decision

    available_targets = allowed_targets.get(decision.action_type, [])
    target = decision.target
    if target is None and pending_external_interaction is not None:
        if pending_external_interaction.target in available_targets:
            target = pending_external_interaction.target
    if target is None and len(available_targets) == 1:
        target = available_targets[0]
    if decision.action_type in {"tool", "mcp", "skill"} and target not in available_targets:
        return AutoActionDecision(action_type="llm", respond_with_llm=True)
    return decision.model_copy(update={"target": target})


def _extract_json_object(*, text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            stripped = stripped[first_brace:last_brace + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            return None
        try:
            payload = json.loads(stripped[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_routed_next_action(
    *,
    goal: str,
    profile_name: str | None,
    action_type: str,
    target: str | None,
    arguments: dict[str, object],
) -> NextAction:
    if action_type == "tool":
        return NextAction(
            action_type="tool",
            action_target=target,
            action_input={"arguments": arguments},
        )
    if action_type == "mcp":
        return NextAction(
            action_type="mcp",
            action_target=target,
            action_input={"arguments": arguments},
        )
    if action_type == "rag":
        return NextAction(
            action_type="rag",
            action_target=None,
            action_input={"query": str(arguments.get("query", goal))},
        )
    if action_type == "skill":
        return NextAction(
            action_type="skill",
            action_target=target,
            action_input={"skill_name": target} if target else {},
        )
    return NextAction(
        action_type="llm",
        action_target=None,
        action_input={"profile_name": profile_name} if profile_name else {},
    )


def _extract_model_names_from_payload(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []

    raw_items: list[object] = []
    for key in ("data", "models"):
        value = payload.get(key)
        if isinstance(value, list):
            raw_items.extend(value)

    model_names: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        raw_model_name = item.get("id")
        if not isinstance(raw_model_name, str):
            raw_model_name = item.get("name")
        if not isinstance(raw_model_name, str):
            continue
        normalized = raw_model_name.strip()
        if normalized.startswith("models/"):
            normalized = normalized.removeprefix("models/").strip()
        if normalized and normalized not in model_names:
            model_names.append(normalized)

    model_names.sort(key=str.lower)
    return model_names
