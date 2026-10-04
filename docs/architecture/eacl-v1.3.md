# EACL v1.3 active architecture

## Scope

EACL is the only default solver path. It is a bounded host control plane, not a second unconstrained reasoning agent. Every question has isolated state and a hard call/token contract.

## Stage contract

| Stage | Owner | Contract |
| --- | --- | --- |
| Intake | host | Normalize the problem and keep only safe metadata. |
| Route | host | Select direct, structured, or deep risk lane. |
| Solve | model | Produce a bounded candidate-bearing response. |
| Ledger | host | Extract candidates, canonicalize surfaces, retain provenance. |
| Verify | host | Apply only deterministic checks whose domain is supported. |
| Decide | host | Select only a closed candidate or abstain. |
| Finalize | optional OFF model | Repeat the selected value; never recompute it. |
| Serialize | host | Emit the competition-facing `final_response`. |

## Budget

The default configuration allows at most three model calls and 12,288 requested tokens per question. The runner adds an external timeout and one retry for transport failures. The EACL pipeline does not read gold answers, benchmark artifacts, or cross-question state.

## Deliberate removals

The reference-example RAG stack, method-card retriever, sentence-transformer model, Chroma database, and their dedicated evaluation scripts were removed in the v1.3 reshape. They were opt-in historical experiments, not dependencies of the EACL runtime closure, and added roughly 1.4 GB to every checkout.

The experiment results remain in `docs/research/` and `docs/experiments/`; raw model outputs remain in ignored `artifacts/` directories.

## Evidence boundary

The completed proxy221 EACL run is evidence that the pipeline is runnable and auditable. It is not evidence of a net score improvement: the common evaluator reported 106 correct, 12 incorrect, and 103 invalid. The default path is enabled for architecture validation, while score promotion remains subject to a fresh paired evaluation.
