"""MzAgent 第一阶段 ReAct 编排壳。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.action import AvailableAction, NextAction, ReActResult, build_react_result
from ..contracts.context import ContextSnapshot
from ..contracts.state import ReactStatus, StepState

ACTION_PRIORITY = ("skill", "tool", "mcp", "rag", "llm", "clarify", "finish")


class ReActRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    context_snapshot: ContextSnapshot
    available_actions: list[AvailableAction]
    max_steps: int = Field(default=5, ge=0)


class ReActEngine:
    def decide(self, *, request: ReActRequest) -> ReActResult:
        if request.max_steps <= 0:
            return build_react_result(react_status=ReactStatus.DEGRADED)

        if self._plan_is_finished(request.context_snapshot):
            return build_react_result(
                react_status=ReactStatus.RUNNING,
                next_action=NextAction(
                    action_type="finish",
                    action_target=None,
                    action_input={"answer": self._resolve_finish_answer(request)},
                ),
            )

        selected = self._select_action(request=request)
        if selected is None:
            clarify = self._find_action(request.available_actions, "clarify")
            if clarify is not None and clarify.availability == "available":
                return build_react_result(
                    react_status=ReactStatus.RUNNING,
                    next_action=NextAction(
                        action_type="clarify",
                        action_target=None,
                        action_input={"message": "请补充必要信息。"},
                    ),
                )
            return build_react_result(react_status=ReactStatus.BLOCKED)

        return build_react_result(
            react_status=ReactStatus.RUNNING,
            next_action=self._build_next_action(
                goal=request.goal,
                context_snapshot=request.context_snapshot,
                action=selected,
            ),
        )

    def _select_action(self, *, request: ReActRequest) -> AvailableAction | None:
        preferred_skill = request.context_snapshot.skill_context.get("selected_skill")
        preferred_action_type = request.context_snapshot.perception.get("preferred_auto_action_type")
        if isinstance(preferred_action_type, str):
            preferred_action = self._find_action(request.available_actions, preferred_action_type)
            if preferred_action is not None and preferred_action.availability == "available":
                return preferred_action

        for action_type in ACTION_PRIORITY:
            action = self._find_action(request.available_actions, action_type)
            if action is None or action.availability != "available":
                continue
            if action_type == "skill" and preferred_skill and preferred_skill in action.targets:
                return action
            if action_type != "skill":
                return action

        return None

    @staticmethod
    def _find_action(
        actions: list[AvailableAction],
        action_type: str,
    ) -> AvailableAction | None:
        for action in actions:
            if action.action_type == action_type:
                return action
        return None

    def _build_next_action(
        self,
        *,
        goal: str,
        context_snapshot: ContextSnapshot,
        action: AvailableAction,
    ) -> NextAction:
        if action.action_type == "skill":
            preferred_skill = context_snapshot.skill_context.get("selected_skill")
            target = (
                str(preferred_skill)
                if isinstance(preferred_skill, str) and preferred_skill in action.targets
                else self._first_target(action.targets)
            )
            return NextAction(
                action_type="skill",
                action_target=target,
                action_input={"skill_name": target} if target is not None else {},
            )

        if action.action_type == "tool":
            return NextAction(
                action_type="tool",
                action_target=self._first_target(action.targets),
                action_input={
                    "arguments": _build_action_arguments(
                        context_snapshot=context_snapshot,
                        goal=goal,
                        action_type="tool",
                        target=self._first_target(action.targets),
                    )
                },
            )

        if action.action_type == "mcp":
            preferred_mcp_target = context_snapshot.perception.get("preferred_mcp_target")
            resolved_target = (
                str(preferred_mcp_target)
                if isinstance(preferred_mcp_target, str) and preferred_mcp_target in action.targets
                else self._first_target(action.targets)
            )
            return NextAction(
                action_type="mcp",
                action_target=resolved_target,
                action_input={
                    "arguments": _build_action_arguments(
                        context_snapshot=context_snapshot,
                        goal=goal,
                        action_type="mcp",
                        target=resolved_target,
                    )
                },
            )

        if action.action_type == "rag":
            return NextAction(
                action_type="rag",
                action_target=None,
                action_input={"query": goal},
            )

        if action.action_type == "llm":
            messages = _build_conversation_messages(
                context_snapshot=context_snapshot,
                goal=goal,
            )
            llm_action_input = _build_action_arguments(
                context_snapshot=context_snapshot,
                goal=goal,
                action_type="llm",
                target=None,
            )
            llm_action_input["messages"] = messages
            return NextAction(
                action_type="llm",
                action_target=None,
                action_input=llm_action_input,
            )

        if action.action_type == "clarify":
            return NextAction(
                action_type="clarify",
                action_target=None,
                action_input={"message": "请补充必要信息。"},
            )

        return NextAction(
            action_type="finish",
            action_target=None,
            action_input={"answer": self._resolve_finish_answer_from_snapshot(context_snapshot, goal)},
        )

    @staticmethod
    def _first_target(targets: list[str]) -> str | None:
        return targets[0] if targets else None

    @staticmethod
    def _plan_is_finished(context_snapshot: ContextSnapshot) -> bool:
        current_plan = context_snapshot.current_plan
        if current_plan is None:
            return False
        return bool(current_plan.step_state) and all(
            state is StepState.DONE for state in current_plan.step_state.values()
        )

    def _resolve_finish_answer(self, request: ReActRequest) -> str:
        return self._resolve_finish_answer_from_snapshot(request.context_snapshot, request.goal)

    @staticmethod
    def _resolve_finish_answer_from_snapshot(
        context_snapshot: ContextSnapshot,
        goal: str,
    ) -> str:
        last_observation = context_snapshot.last_observation or {}
        draft_answer = last_observation.get("draft_answer")
        final_answer = last_observation.get("final_answer")
        if isinstance(final_answer, str) and final_answer:
            return final_answer
        if isinstance(draft_answer, str) and draft_answer:
            return draft_answer
        return f"任务已完成：{goal}"


def _build_conversation_messages(
    *,
    context_snapshot: ContextSnapshot,
    goal: str,
) -> list[dict[str, str]]:
    history = context_snapshot.perception.get("conversation_messages", [])
    messages: list[dict[str, str]] = []
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": goal})
    return messages


def _build_action_arguments(
    *,
    context_snapshot: ContextSnapshot,
    goal: str,
    action_type: str,
    target: str | None,
) -> dict[str, object]:
    perception = context_snapshot.perception
    available_arguments = perception.get("available_action_arguments")
    if isinstance(available_arguments, dict):
        action_arguments = available_arguments.get(action_type)
        if isinstance(action_arguments, dict):
            if target is not None:
                target_arguments = action_arguments.get(target)
                if isinstance(target_arguments, dict):
                    return dict(target_arguments)
            default_arguments = action_arguments.get("__default__")
            if isinstance(default_arguments, dict):
                return dict(default_arguments)

    pending_arguments = perception.get("pending_action_arguments")
    if isinstance(pending_arguments, dict):
        return dict(pending_arguments)
    return {}
