# Harr 0.3.1

Harr 0.3.1 is a focused packaging hotfix for the 0.3.0 Doctor release.

The Debian entrypoint now explicitly marks setup as a package installation before delegating to the packaged Harr runtime. This fixes install provenance incorrectly recording `"install_type": "source"` after `harr setup --harr-only` on a Debian-installed Harr.

The package entrypoint is now a small relocatable wrapper rather than a symlink. It preserves normal `harr` behavior, works in the release package extraction smoke test, and exports only `HARR_INSTALL_TYPE=package` before executing the packaged runtime.

No Doctor health semantics, MCP selection, credentials, named Ein configuration, or LeanCTX version change in this hotfix. Harr Doctor remains the 0.3 feature; R2/R3 repair work remains deferred in `docs/HARR_DOCTOR_DEFERRED.md`.

After upgrading, run:

```text
harr setup --harr-only
harr doctor
```

The setup refresh preserves saved MCP selection, secrets and named Ein instances while rewriting the provenance manifest with `install_type=package`.
