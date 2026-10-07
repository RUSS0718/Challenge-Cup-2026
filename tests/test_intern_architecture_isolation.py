"""Guard the active import chain and expose a deterministic source comparison probe."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


PROBE = r'''import importlib.abc
import json
from pathlib import Path
import sys
import time

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))

class LegacyBlocker(importlib.abc.MetaPathFinder):
    """Reject all legacy runtime imports except the reviewed persistence utility."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("reasoning_agent.") and fullname != "reasoning_agent.artifacts":
            raise AssertionError("legacy runtime import: " + fullname)
        if fullname.split(".")[0] in {"reference_reasoning_runtime", "causal_demo", "causal_lens", "bank", "deterministic_math", "pot_executor", "sympy_adapter", "substitution_check"}:
            raise AssertionError("legacy runtime import: " + fullname)
        return None

sys.meta_path.insert(0, LegacyBlocker())
from user_agent import ReasoningAgent

# Elapsed timing is held constant to compare decisions rather than machine speed.
time.monotonic = lambda: 100.0
time.perf_counter = lambda: 100.0

class Client:
    """Supply frozen responses and capture the complete public call contract."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        value = self.responses.pop(0) if self.responses else "最终答案：2"
        if value == "__error__":
            raise RuntimeError("unavailable")
        return value

results = []
for name, responses, metadata in [
    ("complete", ["最终答案：2"], {}),
    ("failure", ["__error__"], {}),
    ("empty", [""], {}),
    ("continuation", ["尚未得到结论", "最终答案：2"], {}),
    ("extended_budget", ["最终答案：2"], {"idx": 33}),
]:
    client = Client(responses)
    result = ReasoningAgent(client=client).solve("计算 1+1", metadata)
    results.append({"case": name, "result": result, "calls": client.calls})

if (root / "main.py").is_file():
    import main
    assert not hasattr(main, "build_profile_config")
    assert main.ReasoningAgent is ReasoningAgent

legacy_loaded = sorted(name for name in sys.modules if name.startswith("reasoning_agent.") and name != "reasoning_agent.artifacts")
assert not legacy_loaded, legacy_loaded
print(json.dumps(results, ensure_ascii=False, sort_keys=True))
'''


def probe(root):
    """Return request/output decisions from a fresh process rooted at one snapshot."""
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-I", "-c", PROBE, str(root)],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    return json.loads(completed.stdout)


class ArchitectureIsolationTest(unittest.TestCase):
    """Keep legacy imports and profile routing out of the current entry."""

    def test_entry_and_runner_without_legacy_runtime(self):
        """Exercise completion, failures, continuation, and extended budget with blocked legacy imports."""
        results = probe(Path(__file__).resolve().parents[1])
        self.assertEqual(5, len(results))
        for item in results:
            self.assertTrue(item["result"]["final_response"])
            self.assertLessEqual(len(item["calls"]), 6)
        self.assertGreater(len(results[3]["calls"]), 1)

    def test_cli_rejects_legacy_profile(self):
        """Old routing cannot be selected through the supported local CLI."""
        from unittest.mock import patch
        import main
        with patch.object(sys, "argv", ["main.py", "--input_file", "input", "--output_dir", "output", "--profile", "fsdf"]):
            with self.assertRaises(SystemExit) as context:
                main.parse_args()
        self.assertEqual(2, context.exception.code)


if __name__ == "__main__":
    unittest.main()
