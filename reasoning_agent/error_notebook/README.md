# Offline reviewed-error notebook

This directory is intentionally outside the runtime solve path.  The allowed
flow is:

`trace export → human review → generalise a mistake → held-out validation → Skill admission`

Entries are JSONL records validated by `scripts/validate_error_notebook.py`.
They contain a generalised mistake pattern and a corrective rule, not raw
prompts, model responses, reference answers, or hidden-judge fields.  A
`validated` entry must record at least one held-out case.  The validator is
stdlib-only and never writes to the notebook or contacts a network.
