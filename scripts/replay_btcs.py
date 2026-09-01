"""Run the BTCS transcript smoke cases without a network client."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from user_agent import AgentConfig, ReasoningAgent
from tests.support.replay_client import ReplayClient, load_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(load_cases()), help="run one named case")
    parser.add_argument(
        "--protocol-mode",
        choices=("btcs_frame_v2",),
        default="btcs_frame_v2",
    )
    args = parser.parse_args()
    cases = load_cases()
    selected = {args.case: cases[args.case]} if args.case else cases
    for name, responses in selected.items():
        client = ReplayClient(responses)
        agent = ReasoningAgent(
            client,
            AgentConfig(
                protocol_mode=args.protocol_mode,
                enable_time_convergence=False,
                btcs_retry_base_delay_seconds=0.0,
            ),
        )
        result = agent.solve("计算 3+4。", {})
        print(
            json.dumps(
                {
                    "case": name,
                    "protocol_mode": args.protocol_mode,
                    "final_response_nonempty": bool(result.get("final_response")),
                    "logical_calls": result["trace"][-1].get("logical_calls"),
                    "http_attempts": result["trace"][-1].get("http_attempts"),
                    "replay_calls": len(client.calls),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
