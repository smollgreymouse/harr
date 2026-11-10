# Harr 0.3.9

Harr 0.3.9 extends the optional Kibana MCP with safe multi-endpoint support.

`KIBANA_URL` may now contain one URL or a comma/whitespace-separated list of trusted Kibana endpoints. The first URL is the default. Network tools keep the optional `kibana_url` argument, but it may select only an endpoint already present in `KIBANA_URL`.

The pinned `smollgreymouse/kibana-agent` fork adds `list_kibana_endpoints`, which exposes only the configured URLs and the default marker so the model can choose an environment without seeing credentials. `KIBANA_API_KEY` may contain one shared key or one comma-separated key per configured URL in the same order; the MCP selects the matching key internally.

The previous single-URL/single-token configuration remains compatible. The separate `KIBANA_MCP_ALLOWED_URLS` setting introduced during development is removed; `KIBANA_URL` itself is now the trusted endpoint list.

This release pins kibana-agent at `6334b36184d2d598d52339f6322fa1742b279f2f`. The fork test suite passes 253 tests, and Harr's MCP registry/selection tests plus the clean harness takeover/rollback test pass with the new contract.
