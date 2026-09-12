# Reference RAG runtime bundle

This directory is the offline retrieval payload used by the submission agent.

- Embedding model: `Qwen/Qwen3-Embedding-0.6B`.
- Vector store: Chroma collection `math_rag_v1`, 15,383 records.
- Runtime network access: none.
- Device policy: use CUDA when available and valid; otherwise use CPU.
- Generated Python execution: disabled.

The two files larger than ordinary Git hosting limits are stored as deterministic
64 MiB shards. `reference_reasoning_runtime.assets.ensure_runtime_assets()` joins
them under the system temporary directory and verifies the SHA256 values in
`manifest.json` before model or database loading.

`model/README.md` is the upstream model card retained with the model files.
