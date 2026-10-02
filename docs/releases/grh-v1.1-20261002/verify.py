"""Verify the recorded v1.1 sources and public submission entry offline."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import user_agent


def solve_once(index):
    """Exercise the public client contract without credentials or remote calls."""
    class Client:
        """Provide the three public arguments supported by the platform client."""
        def chat(self, messages, temperature, max_tokens):
            """Return an explicit answer for an entry-contract smoke check."""
            return "Final answer: 2"
    result = user_agent.ReasoningAgent(client=Client()).solve("Compute 1+1", {"idx": index})
    assert isinstance(result["final_response"], str) and result["final_response"].strip()
    json.dumps(result)
    return result["final_response"]


def main():
    """Check byte hashes, experimental defaults, and three concurrent solves."""
    manifest = json.loads(Path(__file__).with_name("experiment_manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["runtime_file_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    config = user_agent.SUBMISSION_CONFIG
    assert user_agent.SUBMISSION_MODE == "arm-v2.1.3-off"
    assert config.arm_harness_version == "v2.1.3"
    assert config.arm_solver_reasoning_mode == "off"
    assert config.arm_trust_policy == "positive_evidence"
    assert config.enable_constraint_fit_harness and config.enable_constraint_fit_deep_lane
    assert not any((config.enable_constraint_fit_hybrid_router,
                    config.enable_temporary_answer_bank, config.enable_reference_rag,
                    config.enable_method_rag, config.enable_reference_skills,
                    config.arm_enable_skill_guidance))
    assert config.harness_bank_mode == "off"
    assert config.arm_adaptive_max_calls == config.arm_deep_max_calls == 3
    assert config.arm_adaptive_token_budget == config.arm_deep_token_budget == 16384
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert len(list(pool.map(solve_once, range(3)))) == 3
    print("PASS: 10 exact experiment hashes; v1.1 defaults; 3 concurrent public-client solves")


if __name__ == "__main__":
    main()
