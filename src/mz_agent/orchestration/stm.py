"""MzAgent 第一阶段 STM 编排壳。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..contracts.context import ContextSnapshot
from ..contracts.state import ReactStatus
from ..runtime.writeback import WritebackRecord


class STMState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_snapshot: ContextSnapshot
    last_writeback: WritebackRecord | None = None
    writeback_count: int = 0


class InMemorySTM:
    def __init__(self, *, initial_snapshot: ContextSnapshot | None = None) -> None:
        self._state = STMState(
            context_snapshot=initial_snapshot or ContextSnapshot(current_plan=None)
        )

    def latest_context_snapshot(self) -> ContextSnapshot:
        return self._state.context_snapshot

    def replace_context_snapshot(self, *, snapshot: ContextSnapshot) -> ContextSnapshot:
        self._state = STMState(
            context_snapshot=snapshot,
            last_writeback=self._state.last_writeback,
            writeback_count=self._state.writeback_count,
        )
        return self._state.context_snapshot

    def last_writeback(self) -> WritebackRecord | None:
        return self._state.last_writeback

    def apply_writeback(self, *, record: WritebackRecord) -> ContextSnapshot:
        snapshot = self._state.context_snapshot
        current_plan = snapshot.current_plan
        if current_plan is not None:
            if record.react_status is ReactStatus.FINISHED:
                current_plan = current_plan.model_copy(update={"current_step": None})
            elif record.current_step is not None:
                current_plan = current_plan.model_copy(update={"current_step": record.current_step})

        stm_state = dict(snapshot.stm)
        stm_state["last_writeback_stage"] = record.stage
        stm_state["last_react_status"] = record.react_status.value
        if record.final_answer is not None:
            stm_state["last_final_answer"] = record.final_answer

        perception_state = _apply_conversation_writeback(
            snapshot=snapshot,
            record=record,
        )

        observation = record.observation
        if observation is None and record.final_answer is not None:
            observation = {
                "source": "answer",
                "output_text": record.final_answer,
            }

        updated_snapshot = snapshot.model_copy(
            update={
                "current_plan": current_plan,
                "perception": perception_state,
                "stm": stm_state,
                "last_observation": observation,
            }
        )
        self._state = STMState(
            context_snapshot=updated_snapshot,
            last_writeback=record,
            writeback_count=self._state.writeback_count + 1,
        )
        return updated_snapshot


class FileBackedSTM(InMemorySTM):
    def __init__(self, *, storage_path: str | Path) -> None:
        self._storage_path = Path(storage_path).expanduser().resolve()
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        super().__init__(initial_snapshot=state.context_snapshot)
        self._state = state

    def replace_context_snapshot(self, *, snapshot: ContextSnapshot) -> ContextSnapshot:
        updated = super().replace_context_snapshot(snapshot=snapshot)
        self._persist_state()
        return updated

    def apply_writeback(self, *, record: WritebackRecord) -> ContextSnapshot:
        updated = super().apply_writeback(record=record)
        self._persist_state()
        return updated

    def _load_state(self) -> STMState:
        if not self._storage_path.exists():
            return STMState(context_snapshot=ContextSnapshot(current_plan=None))
        with self._storage_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return STMState.model_validate(payload)

    def _persist_state(self) -> None:
        payload = self._state.model_dump(mode="json")
        temp_path = self._storage_path.with_suffix(f"{self._storage_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, self._storage_path)


def _apply_conversation_writeback(
    *,
    snapshot: ContextSnapshot,
    record: WritebackRecord,
) -> dict[str, object]:
    perception_state = dict(snapshot.perception)
    history = _read_conversation_history(perception=snapshot.perception)
    round_id = perception_state.get("pending_round_id")

    pending_user_message = perception_state.get("pending_user_message")
    if isinstance(pending_user_message, str) and pending_user_message:
        message: dict[str, str] = {"role": "user", "content": pending_user_message}
        if isinstance(round_id, str) and round_id:
            message["round_id"] = round_id
        history.append(message)

    assistant_text = _extract_assistant_text(record=record)
    if assistant_text:
        message = {"role": "assistant", "content": assistant_text}
        if isinstance(round_id, str) and round_id:
            message["round_id"] = round_id
        history.append(message)

    perception_state["conversation_messages"] = history
    perception_state.pop("pending_user_message", None)
    perception_state.pop("pending_round_id", None)
    return perception_state


def _read_conversation_history(*, perception: dict[str, object]) -> list[dict[str, str]]:
    raw_history = perception.get("conversation_messages", [])
    history: list[dict[str, str]] = []
    if not isinstance(raw_history, list):
        return history
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if isinstance(role, str) and isinstance(content, str):
            message = {"role": role, "content": content}
            round_id = item.get("round_id")
            if isinstance(round_id, str) and round_id:
                message["round_id"] = round_id
            history.append(message)
    return history


def _extract_assistant_text(*, record: WritebackRecord) -> str | None:
    if record.final_answer:
        return record.final_answer

    observation = record.observation or {}
    source = observation.get("source")
    if source == "answer":
        output_text = observation.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

    if source == "llm":
        response = observation.get("response")
        if isinstance(response, dict):
            content_blocks = response.get("content_blocks", [])
            if isinstance(content_blocks, list):
                texts: list[str] = []
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "text":
                        continue
                    content = block.get("content")
                    if isinstance(content, str) and content:
                        texts.append(content)
                if texts:
                    return "\n".join(texts)

    if source in {"tool", "mcp"}:
        result = observation.get("result")
        if isinstance(result, dict):
            text = result.get("text")
            if isinstance(text, str) and text:
                return text

    if source in {"rag", "skill"}:
        result = observation.get("result")
        if result is not None:
            return json.dumps(result, ensure_ascii=False)
    return None
