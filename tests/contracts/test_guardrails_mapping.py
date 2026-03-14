from mz_agent.contracts.action import AvailableAction, NextAction, build_react_result
from mz_agent.contracts.guardrails import map_guardrail_decision
from mz_agent.contracts.state import GuardrailsDecisionKind, ReactStatus
from mz_agent.runtime.errors import DomainValidationError


def test_available_action_targets_default_to_empty_list() -> None:
    action = AvailableAction(action_type="tool", availability="available")
    assert action.targets == []


def test_next_action_input_defaults_to_empty_object() -> None:
    next_action = NextAction(action_type="tool", action_target="search_docs")
    assert next_action.action_input == {}


def test_guardrails_allow_action_keeps_running_result() -> None:
    result = map_guardrail_decision(
        decision=GuardrailsDecisionKind.ALLOW,
        candidate_action=NextAction(action_type="tool", action_target="search_docs"),
    )

    assert result.react_status is ReactStatus.RUNNING
    assert result.next_action is not None
    assert result.next_action.action_type == "tool"
    assert result.final_answer is None


def test_guardrails_block_and_degrade_use_single_encoding() -> None:
    blocked = map_guardrail_decision(decision=GuardrailsDecisionKind.BLOCK)
    degraded = map_guardrail_decision(decision=GuardrailsDecisionKind.DEGRADE)

    assert blocked.model_dump(mode="json") == {
        "next_action": None,
        "final_answer": None,
        "react_status": "blocked",
    }
    assert degraded.model_dump(mode="json") == {
        "next_action": None,
        "final_answer": None,
        "react_status": "degraded",
    }


def test_guardrails_clarify_only_uses_action_type() -> None:
    result = map_guardrail_decision(decision=GuardrailsDecisionKind.CLARIFY)

    assert result.react_status is ReactStatus.RUNNING
    assert result.next_action is not None
    assert result.next_action.action_type == "clarify"
    assert result.next_action.action_target is None
    assert result.final_answer is None


def test_finished_result_requires_final_answer_and_no_next_action() -> None:
    result = build_react_result(
        react_status=ReactStatus.FINISHED,
        final_answer="已完成",
    )

    assert result.model_dump(mode="json") == {
        "next_action": None,
        "final_answer": "已完成",
        "react_status": "finished",
    }

    allow_answer_result = map_guardrail_decision(
        decision=GuardrailsDecisionKind.ALLOW,
        candidate_answer="已完成",
    )
    assert allow_answer_result.model_dump(mode="json") == {
        "next_action": None,
        "final_answer": "已完成",
        "react_status": "finished",
    }

    try:
        build_react_result(
            react_status=ReactStatus.FINISHED,
            next_action=NextAction(action_type="finish", action_target=None),
            final_answer="已完成",
        )
    except DomainValidationError as exc:
        assert "完成态结果不得继续保留动作" in str(exc)
    else:
        raise AssertionError("完成态错误地保留了动作。")
