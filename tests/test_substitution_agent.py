import unittest

from user_agent import AgentConfig, ReasoningAgent


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _candidate(candidate_id, answer, evidence=None):
    return {
        "candidate_id": candidate_id,
        "answer": answer,
        "normalized_answer": answer,
        "evidence": evidence or [],
        "verification_status": "unverified",
        "model_calls_used": 1,
    }


class SubstitutionEvidenceSelectionTest(unittest.TestCase):
    def test_substitution_evidence_uses_the_existing_tool_rank_channel(self):
        candidates = [
            _candidate(0, "1", [{"source": "substitution_check", "claim_status": "REFUTED"}]),
            _candidate(1, "2", [{"source": "substitution_check", "claim_status": "SUPPORTED"}]),
        ]

        selected = ReasoningAgent._select_candidate(candidates)

        self.assertEqual("2", selected["answer"])
        self.assertEqual("substitution_check_evidence", selected["selection_basis"])

    def test_enabled_variant_generates_program_and_attaches_only_compact_evidence(self):
        client = FakeClient(["最终答案：7", "print(candidate == 7)"])
        agent = ReasoningAgent(
            client,
            AgentConfig(
                policy_sample_times=1,
                max_model_calls=2,
                enable_l0_extended_tokens=False,
                enable_substitution_check=True,
                enable_step_verification=False,
            ),
        )

        result = agent.solve("计算 3+4", {})

        self.assertEqual(2, len(client.calls))
        event = next(entry for entry in result["trace"] if entry["step"] == "substitution_check")
        self.assertEqual("SUPPORTED", event["claim_status"])
        self.assertEqual("7", result["extracted_answer"])
        self.assertNotIn("candidate == 7", str(result["trace"]))
