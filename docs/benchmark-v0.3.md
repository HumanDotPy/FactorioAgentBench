# Factorio RLVR benchmark 0.3 development catalog

Status: development catalog, pinned to Factorio 2.0.77.

Version `0.3.0-dev` replaces `0.2.0-dev` as the current development catalog.
It refreshes the engine contract data for Factorio 2.0.77 and updates the tool
contracts for adjacent-pole placement, offshore-pump connection, and belt
routing. The versioned catalog is generated at
`benchmark/manifests/benchmark-0.3.0-dev.json`.

The `0.2.0-dev` manifest and run records remain available as historical
Factorio 2.0.73 artifacts. Their fingerprints describe the catalog used when
those runs were collected. They are not baselines for `0.3.0-dev`; no v0.3
baseline has been published yet.

Generate or validate current artifacts with:

```bash
fle-benchmark-results manifest benchmark/manifests/benchmark-0.3.0-dev.json
fle-benchmark-results validate benchmark/results/<current-run>.json
```
