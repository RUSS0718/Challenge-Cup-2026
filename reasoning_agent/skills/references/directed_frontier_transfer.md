# Directed frontier transfer reference

Use this reference only after the host route has identified a directed,
fixed-width strip or periodic cylinder whose path count is local by column.
Instantiate the symbols from the problem before using any transition.

## Execution order

1. Normalize the vertex range, the period, and every edge direction by
   expanding the algebra before naming the direction. For example, the pair
   `x_i - x_{i+1} in {-1, n-1}` means `x_{i+1}=x_i+1` for ordinary columns and
   the wrap `n-1 -> 0`; it does not mean `x_i -> x_i-1`. A horizontal condition
   that advances a coordinate modulo `n` is directed; do not add the reverse
   edge unless the statement gives it.
2. Apply cheap invariants first: bipartite coloring, endpoint parity, vertex
   counts, and any conservation law. For a path with `L` edges, endpoints are
   opposite colors when `L` is odd and the same color when `L` is even. Use
   this literal parity rule to remove impossible endpoint states, not to
   replace the count.
3. Scan one column at a time. Let `I_j` be the rows whose horizontal edge
   enters column `j`, and `O_j` the rows whose horizontal edge leaves it.
   Carry path connectivity labels with these masks; a degree-valid state that
   closes a cycle before the required endpoint is rejected.
4. Treat the start column and end column as separate boundary transitions.
   For a periodic strip, close the scan with `O_last = I_first`. The endpoint
   column is a state choice unless parity proves it impossible; never assume it
   is the final column.
5. Enumerate local vertical choices to build the finite transition table.
   Iterate the table, record the recurrence or closed form, and check at least
   two smaller widths by direct enumeration before presenting the final value.

## Adaptation guardrails

- The frontier is allowed to cross a column boundary while another path
  segment remains open. Use connectivity state to manage that case.
- A row-wise snake is one possible transition pattern, not a default theorem.
- The reference supplies a method. It does not supply an answer, a fixed
  width, a fixed endpoint, or a problem-specific transition count.
- Finish only after the recurrence is closed and one unique final answer is
  emitted.
