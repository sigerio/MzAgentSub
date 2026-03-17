"""MzAgent 共享运行时入口。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from ..adapters import AdapterHub, LLMAdapter, MCPAdapter, ToolAdapter
from ..contracts.action import AvailableAction, ActionAvailability
from ..contracts.context import ContextSnapshot, ExecutionContext
from ..contracts.tooling import ToolDefinition
from ..orchestration import FileBackedSTM, Pipeline, PipelineRoundResult


class RuntimeOptions(SimpleNamespace):
    live_llm: bool
    stm_path: str
    draft_answer: str
    session_id: str
    request_prefix: str
    trace_prefix: str
    profile_name: str | None

    def __init__(
        self,
        *,
        live_llm: bool = False,
        stm_path: str = ".mz_agent/stm_state.json",
        draft_answer: str = "任务已收束",
        session_id: str = "sess_cli",
        request_prefix: str = "req_cli",
        trace_prefix: str = "trace_cli",
        profile_name: str | None = None,
    ) -> None:
        super().__init__(
            live_llm=live_llm,
            stm_path=stm_path,
            draft_answer=draft_answer,
            session_id=session_id,
            request_prefix=request_prefix,
            trace_prefix=trace_prefix,
            profile_name=profile_name,
        )

    @classmethod
    def from_namespace(cls, namespace: object) -> "RuntimeOptions":
        return cls(
            live_llm=bool(getattr(namespace, "live_llm", False)),
            stm_path=str(getattr(namespace, "stm_path", ".mz_agent/stm_state.json")),
            draft_answer=str(getattr(namespace, "draft_answer", "任务已收束")),
            session_id=str(getattr(namespace, "session_id", "sess_cli")),
            request_prefix=str(getattr(namespace, "request_prefix", "req_cli")),
            trace_prefix=str(getattr(namespace, "trace_prefix", "trace_cli")),
            profile_name=(
                str(getattr(namespace, "llm_profile", "")).strip() or None
                if hasattr(namespace, "llm_profile")
                else None
            ),
        )


def build_runtime(
    *,
    options: RuntimeOptions,
    project_root: Path,
) -> tuple[Pipeline, FileBackedSTM]:
    tool_adapter = ToolAdapter()
    tool_adapter.register(
        definition=ToolDefinition(
            name="search_docs",
            description="搜索文档",
            input_schema={"type": "object", "required": []},
            permission_domain="docs",
            risk_level="low",
            idempotent=True,
            requires_confirmation=False,
            handler=lambda query="": {
                "text": f"已执行搜索：{query}" if query else "已执行搜索",
                "data": {"hits": 1, "query": query},
            },
        )
    )

    adapters = AdapterHub(
        tool=tool_adapter,
        llm=LLMAdapter(project_root=project_root, live_mode=options.live_llm),
        mcp=MCPAdapter(project_root=project_root),
    )
    stm = FileBackedSTM(storage_path=project_root / options.stm_path)
    pipeline = Pipeline(adapters=adapters, stm=stm)
    return pipeline, stm


def run_single_round(
    *,
    options: RuntimeOptions,
    pipeline: Pipeline,
    stm: FileBackedSTM,
    goal: str,
    action_type: str,
    target: str | None,
    profile_name: str | None = None,
    enabled_capabilities: list[str] | None = None,
    enabled_tools: list[str] | None = None,
    enabled_mcp: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    rag_enabled: bool = False,
    round_id: str | None = None,
) -> PipelineRoundResult:
    snapshot = stm.latest_context_snapshot()
    snapshot = prepare_snapshot_for_round(
        snapshot=snapshot,
        goal=goal,
        action_type=action_type,
        target=target,
        profile_name=profile_name or options.profile_name,
        enabled_capabilities=enabled_capabilities or [],
        enabled_tools=enabled_tools or [],
        enabled_mcp=enabled_mcp or [],
        enabled_skills=enabled_skills or [],
        rag_enabled=rag_enabled,
        round_id=round_id,
        draft_answer=options.draft_answer,
    )

    request_id, trace_id = build_request_identifiers(
        request_prefix=options.request_prefix,
        trace_prefix=options.trace_prefix,
        action_type=action_type,
    )
    execution_context = ExecutionContext(
        request_id=request_id,
        session_id=options.session_id,
        plan_id=snapshot.current_plan.plan_id if snapshot.current_plan is not None else None,
        trace_id=trace_id,
        source="react",
    )
    requested_availability: ActionAvailability = "available"
    available_actions = build_available_actions(
        pipeline=pipeline,
        action_type=action_type,
        target=target,
        enabled_capabilities=enabled_capabilities or [],
        enabled_tools=enabled_tools or [],
        enabled_mcp=enabled_mcp or [],
        enabled_skills=enabled_skills or [],
        rag_enabled=rag_enabled,
    )
    if snapshot.perception.get("clarify_needed") and action_type != "clarify":
        requested_availability = "constrained"
        available_actions = [
            AvailableAction(
                action_type=action.action_type,
                targets=list(action.targets),
                availability=requested_availability,
            )
            if action.action_type != "llm"
            else action
            for action in available_actions
        ]
        available_actions.append(
            AvailableAction(
                action_type="clarify",
                targets=[],
                availability="available",
            )
        )

    return pipeline.run_round(
        goal=goal,
        context_snapshot=snapshot,
        available_actions=available_actions,
        execution_context=execution_context,
    )


def prepare_snapshot_for_round(
    *,
    snapshot: ContextSnapshot,
    goal: str,
    action_type: str,
    target: str | None,
    profile_name: str | None = None,
    enabled_capabilities: list[str] | None = None,
    enabled_tools: list[str] | None = None,
    enabled_mcp: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    rag_enabled: bool = False,
    round_id: str | None = None,
    draft_answer: str,
) -> ContextSnapshot:
    perception = dict(snapshot.perception)
    perception.update(
        build_perception_payload(
            goal=goal,
            action_type=action_type,
            target=target,
            enabled_capabilities=enabled_capabilities or [],
            enabled_tools=enabled_tools or [],
            enabled_mcp=enabled_mcp or [],
            enabled_skills=enabled_skills or [],
            rag_enabled=rag_enabled,
            round_id=round_id,
        )
    )

    pending_action_arguments = build_pending_action_arguments(
        action_type=action_type,
        target=target,
        goal=goal,
        profile_name=profile_name,
    )
    if pending_action_arguments is not None:
        perception["pending_action_arguments"] = pending_action_arguments
    else:
        perception.pop("pending_action_arguments", None)

    available_action_arguments = build_available_action_arguments(
        goal=goal,
        profile_name=profile_name,
        enabled_tools=enabled_tools or [],
        enabled_mcp=enabled_mcp or [],
    )
    if available_action_arguments:
        perception["available_action_arguments"] = available_action_arguments
    else:
        perception.pop("available_action_arguments", None)

    update: dict[str, object] = {"perception": perception}
    if action_type == "finish" and snapshot.last_observation is None:
        update["last_observation"] = {"draft_answer": draft_answer}
    return snapshot.model_copy(update=update)


def build_perception_payload(
    *,
    goal: str,
    action_type: str,
    target: str | None,
    enabled_capabilities: list[str],
    enabled_tools: list[str],
    enabled_mcp: list[str],
    enabled_skills: list[str],
    rag_enabled: bool,
    round_id: str | None,
) -> dict[str, object]:
    normalized_goal = normalize_goal(goal=goal)
    constraints = extract_constraints(goal=normalized_goal)
    intent_summary = extract_intent_summary(
        goal=normalized_goal,
        constraints=constraints,
    )
    clarify_needed, clarify_reason = judge_clarify_needed(
        normalized_goal=normalized_goal,
        action_type=action_type,
        target=target,
        intent_summary=intent_summary,
        enabled_capabilities=enabled_capabilities,
        enabled_tools=enabled_tools,
        enabled_mcp=enabled_mcp,
        enabled_skills=enabled_skills,
        rag_enabled=rag_enabled,
    )
    perception: dict[str, object] = {
        "pending_user_message": goal,
        "normalized_goal": normalized_goal,
        "intent_summary": intent_summary,
        "constraints": constraints,
        "clarify_needed": clarify_needed,
        "requested_action_type": action_type,
        "requested_target": target,
        "enabled_capabilities": list(enabled_capabilities),
        "enabled_tools": list(enabled_tools),
        "enabled_mcp": list(enabled_mcp),
        "enabled_skills": list(enabled_skills),
        "rag_enabled": rag_enabled,
    }
    if round_id:
        perception["pending_round_id"] = round_id
    if clarify_reason is not None:
        perception["clarify_reason"] = clarify_reason
    else:
        perception.pop("clarify_reason", None)
    return perception


def build_pending_action_arguments(
    *,
    action_type: str,
    target: str | None,
    goal: str,
    profile_name: str | None = None,
) -> dict[str, object] | None:
    if action_type == "llm":
        return {"profile_name": profile_name} if profile_name else None
    if action_type == "mcp" and target == "cunzhi:zhi":
        return {"message": goal, "is_markdown": True}
    if action_type == "tool" and target == "search_docs":
        return {"query": goal}
    if action_type in {"tool", "mcp"}:
        return {}
    return None


def build_available_action_arguments(
    *,
    goal: str,
    profile_name: str | None,
    enabled_tools: list[str],
    enabled_mcp: list[str],
) -> dict[str, object]:
    action_arguments: dict[str, object] = {}
    if enabled_tools:
        action_arguments["tool"] = {
            tool_name: build_pending_action_arguments(
                action_type="tool",
                target=tool_name,
                goal=goal,
                profile_name=profile_name,
            )
            or {}
            for tool_name in enabled_tools
        }
    if enabled_mcp:
        action_arguments["mcp"] = {
            mcp_name: build_pending_action_arguments(
                action_type="mcp",
                target=mcp_name,
                goal=goal,
                profile_name=profile_name,
            )
            or {}
            for mcp_name in enabled_mcp
        }
    llm_arguments = build_pending_action_arguments(
        action_type="llm",
        target=None,
        goal=goal,
        profile_name=profile_name,
    )
    if llm_arguments:
        action_arguments["llm"] = {"__default__": llm_arguments}
    return action_arguments


def normalize_goal(*, goal: str) -> str:
    return " ".join(goal.strip().split())


def extract_constraints(*, goal: str) -> list[str]:
    if not goal:
        return []
    segments = [
        segment.strip()
        for segment in re.split(r"[，,。；;\n]+", goal)
        if segment.strip()
    ]
    return [
        segment
        for segment in segments
        if any(keyword in segment for keyword in ("只", "必须", "不要", "不能", "限定", "仅"))
    ]


def extract_intent_summary(*, goal: str, constraints: list[str]) -> str:
    if not goal:
        return ""
    segments = [
        segment.strip()
        for segment in re.split(r"[，,。；;\n]+", goal)
        if segment.strip()
    ]
    intent_segments = [segment for segment in segments if segment not in constraints]
    if not intent_segments:
        return goal
    return "；".join(intent_segments)


def judge_clarify_needed(
    *,
    normalized_goal: str,
    action_type: str,
    target: str | None,
    intent_summary: str,
    enabled_capabilities: list[str],
    enabled_tools: list[str],
    enabled_mcp: list[str],
    enabled_skills: list[str],
    rag_enabled: bool,
) -> tuple[bool, str | None]:
    if not normalized_goal:
        return (True, "目标为空。")
    if action_type == "auto":
        if not enabled_capabilities and not rag_enabled:
            return (True, "自动模式缺少可用能力。")
        if "tool" in enabled_capabilities and not enabled_tools:
            return (True, "自动模式缺少可用 Tool。")
        if "mcp" in enabled_capabilities and not enabled_mcp:
            return (True, "自动模式缺少可用 MCP。")
        if "skill" in enabled_capabilities and not enabled_skills:
            return (True, "自动模式缺少可用 Skill。")
        return (False, None)
    if action_type in {"tool", "mcp", "skill", "rag"} and not target:
        return (True, "缺少动作目标。")
    vague_goals = {"处理一下", "看一下", "搞一下", "弄一下", "帮我处理一下", "帮我看一下"}
    if normalized_goal in vague_goals and not intent_summary:
        return (True, "缺少明确意图。")
    return (False, None)


def build_available_actions(
    *,
    pipeline: Pipeline,
    action_type: str,
    target: str | None,
    enabled_capabilities: list[str],
    enabled_tools: list[str],
    enabled_mcp: list[str],
    enabled_skills: list[str],
    rag_enabled: bool,
) -> list[AvailableAction]:
    if action_type != "auto":
        return [
            AvailableAction(
                action_type=action_type,
                targets=[target] if target else [],
                availability="available",
            )
        ]

    available_actions: list[AvailableAction] = []
    normalized_capabilities = set(enabled_capabilities)

    if "skill" in normalized_capabilities:
        skill_targets = enabled_skills or pipeline.adapters.skill.list_skill_names()
        if skill_targets:
            available_actions.append(
                AvailableAction(
                    action_type="skill",
                    targets=skill_targets,
                    availability="available",
                )
            )

    if "tool" in normalized_capabilities:
        tool_targets = enabled_tools or [
            definition.name for definition in pipeline.adapters.tool.list_definitions()
        ]
        if tool_targets:
            available_actions.append(
                AvailableAction(
                    action_type="tool",
                    targets=tool_targets,
                    availability="available",
                )
            )

    if "mcp" in normalized_capabilities:
        mcp_targets = enabled_mcp or [server.name for server in pipeline.adapters.mcp.list_servers()]
        if mcp_targets:
            available_actions.append(
                AvailableAction(
                    action_type="mcp",
                    targets=mcp_targets,
                    availability="available",
                )
            )

    if "rag" in normalized_capabilities or rag_enabled:
        available_actions.append(
            AvailableAction(
                action_type="rag",
                targets=[],
                availability="available",
            )
        )

    available_actions.append(
        AvailableAction(
            action_type="llm",
            targets=[],
            availability="available",
        )
    )
    return available_actions


def build_request_identifiers(
    *,
    request_prefix: str,
    trace_prefix: str,
    action_type: str,
) -> tuple[str, str]:
    token = uuid4().hex[:8]
    return (
        f"{request_prefix}.{token}",
        f"{trace_prefix}.{action_type}.{token}",
    )


def render_round_result(*, result: PipelineRoundResult) -> str:
    if result.output_text:
        return result.output_text

    observation = result.observation or {}
    source = observation.get("source")

    if source == "llm":
        response = observation.get("response")
        if isinstance(response, dict):
            text = extract_text_from_llm_response(response=response)
            if text:
                return text
        return "LLM 已返回结果，但未提取到文本。"

    if source in {"tool", "mcp"}:
        result_payload = observation.get("result")
        if isinstance(result_payload, dict):
            text = result_payload.get("text")
            if isinstance(text, str) and text:
                return text
            return json.dumps(result_payload, ensure_ascii=False, indent=2)

    if source in {"rag", "skill"}:
        result_payload = observation.get("result")
        return json.dumps(result_payload, ensure_ascii=False, indent=2)

    final_answer = result.react_result.final_answer
    if isinstance(final_answer, str) and final_answer:
        return final_answer

    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def extract_text_from_llm_response(*, response: dict[str, object]) -> str:
    blocks = response.get("content_blocks", [])
    if not isinstance(blocks, list):
        return ""

    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        content = block.get("content")
        if isinstance(content, str) and content:
            texts.append(content)
    return "\n".join(texts)
