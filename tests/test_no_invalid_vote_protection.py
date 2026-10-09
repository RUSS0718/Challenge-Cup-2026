"""Observe optional-path delivery through the official solve boundary."""

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import types
from unittest.mock import patch

import pytest

import user_agent


class ScriptedClient:
    """Return public responses and advance a controlled monotonic clock."""

    def __init__(self, responses, clock):
        """Bind fixed responses to a controlled clock and an empty request log."""
        self.responses = iter(responses)
        self.clock = clock
        self.requests = []

    def chat(self, messages, temperature, max_tokens, **kwargs):
        """Record requests without touching any provider or private client state."""
        self.requests.append((messages, temperature, max_tokens, kwargs))
        self.clock[0] += 60.0
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


@contextmanager
def controlled_runtime(clock):
    """Inject clock/deadline boundaries while retaining real agent control flow."""
    @contextmanager
    def deadline(_seconds):
        """Expose preemptive mode while scripted client faults supply interruption."""
        yield "preemptive"

    with patch("time.monotonic", side_effect=lambda: clock[0]), patch.object(
        user_agent, "_realtime_deadline", deadline
    ):
        yield


def test_first_complete_answer_survives_optional_hard_deadline():
    """A second request deadline delivers the completed first answer."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：2", user_agent._SolveDeadlineExceeded()], clock)
    with controlled_runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve("计算 1+1", {})
    assert result["final_response"] == "2"
    assert len(client.requests) == 2
    json.dumps(result)


def test_complete_optional_majority_keeps_existing_selection_rule():
    """Protection alone preserves the legacy choice among complete candidates."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：2", "最终答案：3", "最终答案：3"], clock)
    with controlled_runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve("给出一个整数", {})
    assert result["final_response"] == "3"
    assert len(client.requests) == 3


@pytest.mark.parametrize("optional", [
    RuntimeError("unavailable"), "", "Working: x=", "最终答案：\\frac{3}{",
    "答案：3\n答案：4", "最终答案：无法确定。", '最终答案：{"answer":"unknown"}',
])
def test_optional_failure_or_fragment_cannot_replace_first_answer(optional):
    """Nonempty fragments and conflicting declarations cannot form vote majorities."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：2"] + [optional] * 8, clock)
    with controlled_runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve("计算 1+1", {})
    assert result["final_response"] == "2"


@pytest.mark.parametrize("problem, complete, partial", [
    ("证明x=1则x²=1", "由x=1，平方得x²=1。\n最终答案：成立。", "最终答案：成立。"),
    ("(1)计算1+1；(2)计算2+2", "最终答案：(1) 2；(2) 4", "最终答案：(1) 3"),
])
def test_assertion_or_partial_multipart_cannot_replace_complete_shape(problem, complete, partial):
    """Answer fragments cannot replace required derivation or missing subanswers."""
    clock = [100.0]
    client = ScriptedClient([complete] + [partial] * 8, clock)
    with controlled_runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve(problem, {})
    assert result["final_response"] == (complete if "证明" in problem else "（1）2；（2）4")


@pytest.mark.parametrize("problem, answer", [
    ("证明：若x=1则x²=1", "由x=1，平方得x²=1。\n最终答案：命题成立。"),
    ("(1)计算1+1；(2)计算2+2", "最终答案：(1) 2；(2) 4"),
])
def test_supported_proof_and_multipart_survive_deadline(problem, answer):
    """Deliver the supported complete shape, including required derivation or parts."""
    clock = [100.0]
    client = ScriptedClient([answer, user_agent._SolveDeadlineExceeded()], clock)
    with controlled_runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve(problem, {})
    expected = answer if "证明" in problem else "（1）2；（2）4"
    assert result["final_response"] == expected


def test_no_complete_candidate_keeps_baseline_deadline_failure():
    """An interruption before any response does not fabricate a retained answer."""
    clock = [100.0]
    client = ScriptedClient([user_agent._SolveDeadlineExceeded()], clock)
    with controlled_runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve("计算 1+1", {})
    assert result["final_response"] == "模型未返回有效解答。\n\n最终答案：无法确定。"
    assert not any(item.get("step") == "complete_incumbent" for item in result["trace"])


def test_structured_placeholder_is_not_reported_as_complete_candidate():
    """A serialized JSON placeholder does not gain protection by being nonempty."""
    clock = [100.0]
    client = ScriptedClient(['最终答案：{"answer":"unknown"}'] * 8, clock)
    with controlled_runtime(clock), patch("time.monotonic", return_value=100.0):
        result = user_agent.ReasoningAgent(client=client).solve("输出JSON答案，计算1+1", {})
    assert not any(item.get("step") == "complete_incumbent" for item in result["trace"])


def test_reused_and_separate_agents_do_not_leak_candidates():
    """A successful solve cannot rescue an unrelated next question or instance."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：2"] * 3 + [user_agent._SolveDeadlineExceeded()], clock)
    agent = user_agent.ReasoningAgent(client=client)
    with controlled_runtime(clock):
        first = agent.solve("计算 1+1", {})
        second = agent.solve("计算 2+2", {})
        third = user_agent.ReasoningAgent(client=ScriptedClient(
            [user_agent._SolveDeadlineExceeded()], clock
        )).solve("计算 3+3", {})
    assert first["final_response"] == "2"
    assert second["final_response"] == third["final_response"] == "模型未返回有效解答。\n\n最终答案：无法确定。"


def test_candidate_identity_is_solve_local_and_exact_output_bound():
    """Replay records bind the complete delivered bytes without logging answer text."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：2"] * 6, clock)
    agent = user_agent.ReasoningAgent(client=client)
    with controlled_runtime(clock):
        first = agent.solve("计算 1+1", {})
        second = agent.solve("计算 1+1", {})
    records = [next(item["content"] for item in result["trace"]
                    if item.get("step") == "complete_incumbent")
               for result in (first, second)]
    assert records[0]["solve_id"] != records[1]["solve_id"]
    assert records[0]["problem_id"] == records[1]["problem_id"]
    # SHA256('2'), independently fixed to exact final_response bytes.
    assert records[0]["candidate_id"] == "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"
    assert "final_response" not in records[0]


@pytest.fixture
def baseline_entry():
    """Load the exact original host Git blob with its unchanged imported core."""
    root = Path(__file__).resolve().parents[1]
    source = subprocess.run(
        ["git", "show", "d09165e1397c6f1be3730dee0fe4c51465a8c6a7:user_agent.py"],
        cwd=root, check=True, capture_output=True,
    ).stdout
    module = types.ModuleType("original_sl_v3_host")
    exec(compile(source, "d09165e:user_agent.py", "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("metadata", [{}, {"idx": 33}, {"idx": 59}, {"idx": 85}, {"idx": 111}])
@pytest.mark.parametrize("responses", [
    ["最终答案：2"] * 8,
    ["尚未得到结论", "最终答案：2"] * 4,
    ["最终答案：2"] + ["答案：3\n答案：4"] * 8,
])
def test_protection_preserves_original_request_vector_and_budget(baseline_entry, metadata, responses):
    """Protection changes retention/eligibility, not prompts, requests or idx budgets."""
    observed = []
    for module in (baseline_entry, user_agent):
        clock = [100.0]
        client = ScriptedClient(responses, clock)
        with controlled_runtime(clock):
            result = module.ReasoningAgent(client=client).solve("计算 1+1", metadata)
        observed.append((client.requests, result))
    assert observed[0][0] == observed[1][0]


@pytest.mark.parametrize("problem, responses", [
    ("计算1+1", ["最终答案：2"] * 8),
    ("证明x=1则x²=1", ["由x=1，平方得x²=1。\n最终答案：成立。"] * 8),
    ("(1)计算1+1；(2)计算2+2", ["最终答案：(1) 2；(2) 4"] * 8),
    ("计算1+1", [RuntimeError("unavailable")] * 8),
    ("计算1+1", ["推导未完成：x="] * 8),
])
def test_single_path_and_no_complete_candidate_keep_original_delivery(baseline_entry, problem, responses):
    """Completed supported shapes and baseline failures retain their result contract."""
    answers = []
    for module in (baseline_entry, user_agent):
        clock = [100.0]
        client = ScriptedClient(responses, clock)
        # Zero elapsed time retains the existing single-path sampling decision.
        with controlled_runtime(clock), patch("time.monotonic", return_value=100.0):
            result = module.ReasoningAgent(client=client).solve(problem, {})
        answers.append(result["final_response"])
    assert answers[0] == answers[1]
