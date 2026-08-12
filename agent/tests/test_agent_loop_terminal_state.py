"""Regression tests for AgentLoop terminal-state result dict (issue #114).

Before the fix, AgentLoop.run() returned a dict missing the `reason` field
on the cancelled and max-iter-failed branches even though state.json on
disk recorded a useful reason. SessionService then surfaced
'Execution failed: unknown' to the chat UI.

These tests exercise both terminal paths with a stubbed LLM so the loop
exits without hitting any real API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from src.agent.loop import AgentLoop
from src.agent.trace import TraceWriter


class _StubLLMResponse:
    """Minimal stand-in for ChatLLM's response object."""

    def __init__(self) -> None:
        self.content = ""
        self.tool_calls: list[Any] = []
        self.reasoning_content: str | None = None
        self.has_tool_calls = False


class _StubLLMNoFinal:
    """LLM stub that always returns an empty answer with no tool calls.

    Triggers the 'pipeline did not complete' branch on the first iteration
    because `final_content` stays empty and no `metrics.csv` is written.
    """

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> _StubLLMResponse:
        return _StubLLMResponse()

    def chat(self, messages: list[dict[str, Any]], **_: Any) -> _StubLLMResponse:
        return _StubLLMResponse()


class _StubLLMCancelMidStream:
    """LLM stub that cancels the loop from inside the LLM call.

    Mimics the user pressing the cancel button while waiting on the
    provider; the loop must surface 'cancelled by user' to the UI.
    """

    def __init__(self, agent_ref: "list[AgentLoop]") -> None:
        self._agent_ref = agent_ref

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> _StubLLMResponse:
        # Set _cancelled on the bound agent so the next loop iteration check
        # picks it up.  We still need a valid response so the current
        # iteration completes cleanly.
        self._agent_ref[0]._cancelled = True
        return _StubLLMResponse()

    def chat(self, messages: list[dict[str, Any]], **_: Any) -> _StubLLMResponse:
        return _StubLLMResponse()


def _build_agent(llm: Any, max_iter: int = 3, tmp_run_dir: Path | None = None) -> AgentLoop:
    """Build an AgentLoop with a real (but empty) registry and a stub LLM."""
    from src.tools import build_registry
    from src.memory.persistent import PersistentMemory

    pm = PersistentMemory()
    agent = AgentLoop(
        registry=build_registry(persistent_memory=pm, include_shell_tools=False),
        llm=llm,
        event_callback=None,
        max_iterations=max_iter,
        persistent_memory=pm,
    )
    if tmp_run_dir is not None:
        tmp_run_dir.mkdir(parents=True, exist_ok=True)
        agent.memory.run_dir = str(tmp_run_dir)
    return agent


def test_failed_terminal_returns_reason_iterations_and_max_iterations(
    tmp_path: Path,
) -> None:
    """When the loop exits without a final answer or metrics.csv, the
    returned dict must carry `reason`, `iterations`, and `max_iterations`
    so SessionService can render an actionable error message."""
    agent = _build_agent(_StubLLMNoFinal(), max_iter=3, tmp_run_dir=tmp_path / "run")

    result = agent.run(user_message="anything")

    assert result["status"] == "failed"
    assert result["reason"] == "reached max iterations (3) without final answer"
    assert result["iterations"] >= 1
    assert result["max_iterations"] == 3


def test_cancelled_terminal_returns_reason(tmp_path: Path) -> None:
    """Cancelled-by-user runs must also surface a meaningful reason."""
    agent_ref: list[AgentLoop] = []
    agent = _build_agent(
        _StubLLMCancelMidStream(agent_ref),
        max_iter=3,
        tmp_run_dir=tmp_path / "run",
    )
    agent_ref.append(agent)

    result = agent.run(user_message="anything")

    assert result["status"] == "cancelled"
    assert result["reason"] == "cancelled by user"
    assert result["max_iterations"] == 3


def test_session_service_renders_meaningful_error_from_result(tmp_path: Path) -> None:
    """End-to-end guard for the original UI symptom in #114: with the new
    `reason` field populated, `result.get('reason', 'unknown')` returns the
    meaningful string SessionService passes to attempt.mark_failed."""
    agent = _build_agent(_StubLLMNoFinal(), max_iter=2, tmp_run_dir=tmp_path / "run")

    result = agent.run(user_message="anything")
    ui_error = result.get("reason", "unknown")

    assert ui_error != "unknown"
    assert "max iterations" in ui_error
    assert "2" in ui_error


class _StubLLMAlwaysToolCalls:
    """LLM stub that returns tool calls until tools=None forces text."""

    def __init__(self) -> None:
        self._counter = 0

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> _StubLLMResponse:
        resp = _StubLLMResponse()
        if tools is not None:
            self._counter += 1
            resp.has_tool_calls = True
            resp.tool_calls = [
                type("TC", (), {"id": f"tc_{self._counter}", "name": "compact", "arguments": {}})()
            ]
        else:
            resp.content = "Final answer from forced text-only."
            resp.has_tool_calls = False
        return resp

    def chat(self, messages: list[dict[str, Any]], **_: Any) -> _StubLLMResponse:
        return _StubLLMResponse()


def test_force_text_only_on_last_iteration(tmp_path: Path) -> None:
    """When the LLM keeps calling tools, the last iteration forces text-only
    output by passing tools=None, producing a final answer instead of failure."""
    agent = _build_agent(
        _StubLLMAlwaysToolCalls(), max_iter=5, tmp_run_dir=tmp_path / "run"
    )
    result = agent.run(user_message="do something")

    assert result["status"] == "success"
    assert "Final answer" in result["content"]
    assert result["iterations"] == 5


class _StubLLMPolicyAnswer:
    def __init__(self, content: str) -> None:
        self.content = content

    def stream_chat(self, messages, tools=None, on_text_chunk=None):
        response = _StubLLMResponse()
        response.content = self.content
        return response

    def chat(self, messages, **kwargs):
        return _StubLLMResponse()


@pytest.mark.parametrize("padding, truncated", [(0, False), (2_100, True)])
def test_answer_audit_preserves_full_result_and_truncated_trace(
    tmp_path: Path, padding: int, truncated: bool,
) -> None:
    content = (
        "시장데이터 기반 기술·밸류에이션 점수: 68/100\n"
        "평가 커버리지: 75/100 배점\n"
        "미평가 항목: investor flow\n"
        "완전한 장기투자 종합점수: 산정 보류\n"
        "Provenance: pykrx_mcp\n"
        "Investor flow: unavailable\n"
        + ("x" * padding)
    )
    run_dir = tmp_path / "run"
    agent = _build_agent(_StubLLMPolicyAnswer(content), tmp_run_dir=run_dir)

    result = agent.run(user_message="005930.KS 종합 분석")
    events = TraceWriter.read(run_dir)
    answer = next(event for event in events if event["type"] == "answer")
    audit = next(event for event in events if event["type"] == "answer_audit")

    assert result["content"] == content
    assert answer["content"] == content[:2_000]
    assert audit["answer_chars"] == len(content)
    assert audit["answer_trace_limit"] == 2_000
    assert audit["answer_trace_truncated"] is truncated
    assert audit["market_data_score_present"] is True
    assert audit["coverage_present"] is True
    assert audit["unevaluated_items_present"] is True
    assert audit["long_term_score_deferred"] is True
    assert audit["provenance_present"] is True
    assert audit["unavailable_present"] is True
