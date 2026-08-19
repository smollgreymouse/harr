# Token-economy benchmark

This is a reproducible record of the initial native-versus-Harr comparison. It
separates persistent tool-schema context, individual tool-result payloads, and
the final prose of a broad repository audit. Counts use the pinned
tiktoken 0.8.0 package and its o200k_base encoding.

## Results

| Measurement | Native/direct | Harr/LeanCTX | Difference |
| --- | ---: | ---: | ---: |
| GitLab MCP tool catalog | 39,873 tokens / 216 tools | 1,328 tokens / 6 core tools | 38,545 fewer / 96.7% |
| Exact installer source read | 1,934 | 2,501 | 567 more / 29.3% |
| Installer symbol search | 490 | 271 | 219 fewer / 44.7% |
| Broad architecture-audit final answer | 3,089 | 3,443 | 354 more / 11.5% |

The strongest measured saving is persistent tool-schema context: LeanCTX
exposes a small stable surface and routes specialized services through it. This
is relevant to input context, not a claim that every individual request is
shorter. The exact source-read pair is intentionally a counterexample:
line-level ctx_read retained the source and added line annotations.

The broad audit used a warm CodeGraph index. It measures only final prose, not
provider usage telemetry, cached tokens, hidden reasoning, or tool-call
envelopes. The answers also differ in language and structure, so its 11.5%
delta must not be attributed solely to routing or compression. Both source
answers are preserved to make qualitative review possible.

## Reproduce local counts

Create an isolated environment, install the pinned dependency, then point the
script at saved payloads:

    python3 -m venv /tmp/harr-token-benchmark
    /tmp/harr-token-benchmark/bin/python -m pip install -r benchmarks/token-economy/requirements.txt
    /tmp/harr-token-benchmark/bin/python benchmarks/token-economy/measure.py --file benchmarks/token-economy/results.json

For a strict A/B comparison, capture the exact native and LeanCTX tool payloads
to files and use repeatable pairs:

    /tmp/harr-token-benchmark/bin/python benchmarks/token-economy/measure.py --pair installer-read native.txt leanctx.txt

The broad-audit responses and their methodology are stored under
architecture-audit-2026-08-19/.
