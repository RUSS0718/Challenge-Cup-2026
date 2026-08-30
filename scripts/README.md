# Scripts

Primary entrypoints:

- `evaluate_protocol_ab.py`: same-window interleaved A/B runner.
- `evaluate_dev.py`: single-profile evaluator.
- `analyze_paired_ab.py`: paired exact analysis; see the experiment spec before formal pooling.
- `validate_freeze_set.py` and `validate_medium_freeze_set.py`: legacy dataset validation.

Other scripts are focused diagnostics or dataset builders. Helpers that require removed `docs/13_2`
artifacts live under `experiments/legacy/scripts/`. Check `docs/excluded_approaches.md` before running
any default-off experiment.
