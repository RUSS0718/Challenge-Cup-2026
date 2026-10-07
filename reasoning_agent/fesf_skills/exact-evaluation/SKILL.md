---
name: exact-evaluation
description: >
  Use when a candidate derivation has reduced the problem to one closed,
  bounded exact arithmetic or symbolic expression and a standalone canonical
  equation claim. Produce one restricted EXACT_EVAL request using the host
  tool and map its result back to that named claim. Do not use when the task
  still requires a proof, derivation, unbounded search, optimization, informal existence
  argument, or geometric interpretation, or when the expression or its scope
  has not been derived.
---

# Exact evaluation

## Preconditions

The candidate already contains a closed arithmetic or symbolic expression with
finite size and a claim that says what the expression establishes. The request
has a precise scope; evaluating it is a check of that scope, not a proof of the
whole problem.

## Inputs

Use the current problem, the selected claim id, the expression, and (when a
comparison is needed) the independently derived expected expression. Keep the
claim id stable and make the scope explicit.

## Procedure

1. Copy the smallest closed expression into the restricted request.
2. First record one standalone canonical equation claim, with no prose,
   labels, units, or conjunctions:
   `C1: <expr>=<expected_or_result>`
3. Emit exactly one request for that claim in this form:
   `EXACT_EVAL: claim_id=<id>; expr=<expression>; expected=<expression>; scope=<scope>`
   Omit `expected` when the result itself is the claim's value.
4. Keep arithmetic operators and symbolic names only; leave every other
   operation for the host to reject.
5. Record which claim the request tests and wait for the host result. Use one
   request per claim and do not issue a request when the expression is open or
   the scope is vague.

## Required artifacts

Provide one `EXACT_EVAL` request and one claim mapping. When deterministic
support/refutation is intended, make the named claim a standalone canonical
equation, `<expr>=<expected>` (or `<expr>=<result>` when `expected` is omitted);
do not append prose or a conjunction. Otherwise the host keeps the claim
`PROPOSED` even if the expression happens to occur in its narrative. The claim
remains `PROPOSED` until the host returns a deterministic result. Never write
the tool result directly as the final answer.

## Verification

Treat `EXACT` as support only within the declared scope and assumptions.
Treat `REFUTED` as a counterexample to the named claim. Check that the result
belongs to the same expression and claim before presenting it to evidence
synthesis. For symbolic division or negative powers, state a complete
nonzero-domain condition for the exact denominator/base (for example
`x != 0` or `x+1 != 0`); a broad phrase such as `for all x` is insufficient.

## Stop/Fallback

If the expression is not closed, the scope is unclear, the host returns
`UNKNOWN`, or the result conflicts with another claim, keep the claim
`UNRESOLVED` and continue with the free branch. Do not invent an expression or
retry with a broader operation.
