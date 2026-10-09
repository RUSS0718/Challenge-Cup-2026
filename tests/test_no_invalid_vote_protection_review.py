"""Protection-stage regressions for proof and multipart completeness."""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
import user_agent
from tests.test_no_invalid_vote_protection import ScriptedClient


@contextmanager
def runtime(clock):
    """Inject deterministic clock/deadline behavior at the public solve boundary."""
    @contextmanager
    def deadline(_seconds):
        """Keep the stage test independent of native signal timers."""
        yield "preemptive"

    with patch("time.monotonic", side_effect=lambda: clock[0]), patch.object(
        user_agent, "_realtime_deadline", deadline
    ):
        yield


def test_proof_multipart_keeps_required_derivation():
    """A bare multipart summary cannot replace a complete proof-bearing answer."""
    clock = [100.0]
    full = "(1) The definition of addition gives 1+1=2.\n(2) 2+2=4.\n最终答案：(1) 2; (2) 4"
    bare = "最终答案：(1) 2; (2) 4"
    client = ScriptedClient([full, bare, bare], clock)
    with runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve(
            "(1) Prove 1+1=2; (2) Compute 2+2", {}
        )
    assert result["final_response"] == full


def test_complete_json_multipart_survives_deadline():
    """Complete numeric JSON parts remain protected through an optional deadline."""
    clock = [100.0]
    client = ScriptedClient(['最终答案：{"1":2,"2":4}', user_agent._SolveDeadlineExceeded()], clock)
    with runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve(
            "(1) Compute 1+1; (2) Compute 2+2", {}
        )
    assert result["final_response"] == '{"1":2,"2":4}'


@pytest.mark.parametrize("problem, complete, empty", [
    ("Give an integer in JSON", '{"answer":2}', '{}'),
    ("Give an integer in JSON", '{"answer":2}', '{"answer":[]}'),
    ("Set x=2 and give the integer x in JSON", '{"answer":2}', '{"answer":[]}'),
    ("(1) Compute 1+1; (2) Compute 2+2", '{"1":2,"2":4}', '{"1":2,"2":[]}'),
    ("(1) Give a set of integers; (2) Compute 2+2", '{"1":[2],"2":4}', '{"1":[2],"2":[]}'),
])
def test_empty_json_answers_cannot_replace_complete_incumbent(problem, complete, empty):
    """Empty containers cannot win completeness by vacuous leaf traversal."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：" + complete] + ["最终答案：" + empty] * 2, clock)
    with runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve(problem, {})
    assert result["final_response"] == complete
    assert len(client.requests) == 3


@pytest.mark.parametrize("problem, answer", [
    ("Give the real solution set of x*x+1=0 as a JSON list", '[]'),
    ("Give the real solution set of x*x+1=0 as a JSON list", '{"roots":[]}'),
    ("求实数解集，以JSON数组返回：x*x+1=0", '[]'),
    ("Give the real solution set of x*x+1=0", 'no solution'),
])
def test_explicit_empty_solution_collection_remains_supported(problem, answer):
    """A requested empty collection or no-solution scalar retains parser compatibility."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：" + answer, user_agent._SolveDeadlineExceeded()], clock)
    with runtime(clock):
        result = user_agent.ReasoningAgent(client=client).solve(problem, {})
    assert result["final_response"] == answer
    assert any(item.get("step") == "complete_incumbent" for item in result["trace"])


@pytest.mark.parametrize("metadata", [{}, {"idx": 1}, {"idx": 33}, {"idx": 59}, {"idx": 85}, {"idx": 111}])
def test_published_entry_keeps_protection_enabled_with_uniform_1150(metadata):
    """Default construction retains an answer on interruption with the main budget."""
    clock = [100.0]
    client = ScriptedClient(["最终答案：2", user_agent._SolveDeadlineExceeded()], clock)
    agent = user_agent.ReasoningAgent(client=client)
    with runtime(clock):
        result = agent.solve("计算 1+1", metadata)
    assert agent._solve_budget_seconds == 1150.0
    assert result["final_response"] == "2"
    assert len(client.requests) == agent._model_calls == 2
    names = {base.__name__ for base in type(agent).__mro__}
    assert "CompleteAnswerProtection" in names
    assert names.isdisjoint({"EarlyDelivery", "EvidenceAwareSelection"})
