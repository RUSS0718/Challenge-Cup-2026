"""Verify the ARM v2.1.4 CFR selector and public client boundary offline."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import user_agent


class StrictPublicClient:
    """Implement only the three-argument official chat contract."""

    def chat(self, messages, temperature, max_tokens):
        """Return a parseable answer without exposing metadata to the model."""
        del messages, temperature, max_tokens
        return "Final answer: 2"


def main() -> None:
    """Check selector, CFR gates, strict client compatibility, and trace hygiene."""
    manifest = json.loads(
        (Path(__file__).with_name("manifest.json")).read_text(encoding="utf-8")
    )
    config = user_agent.SUBMISSION_CONFIG
    for name, expected in manifest["runtime_file_sha256"].items():
        source = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(source).hexdigest() == expected, name
    assert manifest["submission_mode"] == "arm-v2.1.4-cfr"
    assert user_agent.SUBMISSION_MODE == "arm-v2.1.4-cfr"
    assert config.arm_harness_version == "v2.1.4"
    assert config.arm_v2_mode == "selective"
    assert config.arm_solver_reasoning_mode == "off"
    assert config.arm_trust_policy == "positive_evidence"
    assert config.enable_constraint_fit_harness
    assert config.enable_constraint_fit_deep_lane
    assert not config.enable_constraint_fit_hybrid_router
    assert config.arm_enable_targeted_repair and config.arm_enable_fresh_review
    assert config.arm_adaptive_max_calls == config.arm_deep_max_calls == 4
    assert config.arm_adaptive_token_budget == config.arm_deep_token_budget == 16_384
    client = StrictPublicClient()
    result = user_agent.ReasoningAgent(client=client).solve(
        "Compute 1+1", {"idx": "smoke", "gold": "SECRET_GOLD"}
    )
    assert result["final_response"].strip()
    assert not any(item.get("stage") == "legacy_backend" for item in result["trace"])
    encoded = json.dumps(result, ensure_ascii=False)
    assert "SECRET_GOLD" not in encoded
    print("PASS: ARM v2.1.4 CFR selector, strict public client, and trace hygiene")


if __name__ == "__main__":
    main()
