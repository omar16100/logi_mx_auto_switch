# Plan: CI, repo hygiene, and third-party license notice (27 Sep 2026)

Status: **implemented**. Part 1 (PR #1, merged): CI, docs, hygiene. Part 2 (PR #2): GPL-3.0
notice and corresponding source for the vendored `bin/hidapitester`.

## Goal

Make "tests pass" verifiable on GitHub, bring the docs in line with the merged 0.1.1 and
0.2.0 code, and ship the license material that the vendored GPL-3.0 binary needs.

## Part 1: CI and hygiene

- `.github/workflows/ci.yml`: ubuntu runner, `actions/checkout@v7`,
  `astral-sh/setup-uv@v10.2.0` (setup-uv publishes no floating major tag after v7),
  `uv run --locked pytest -v`. The suite needs no HID access (captured device output, fake
  transport, injectable clock), so no macOS runner is required.
- `pyproject.toml`: pytest moved into a `dev` dependency group so `uv run pytest` works;
  `uv.lock` refreshed (it still recorded version 0.1.0).
- `.gitignore`: `*.bak-*` (local editor backups of `logi_mx_switch.py`) and `.pytest_cache/`.
- Docs: the 10 Jul push reliability plan (previously an untracked `docs/plans/` file) is
  now [10072026_push_mouse_reliability_plan.md](10072026_push_mouse_reliability_plan.md),
  extended with the 17 Jul fast path, scrubbed of machine names, and registered in
  [index.md](index.md). [c4model.md](c4model.md) updated for the current `push_mouse`,
  the index cache, and CI. README test count corrected from 32 to 52.

## Part 2: vendored hidapitester (GPL-3.0)

`bin/hidapitester` is a third-party GPL-3.0 program invoked as a separate process. Plan:
record its exact provenance, add the GPL-3.0 text, a notice with version, upstream commit,
and build steps, hidapi's license notice, and the exact source archives under
`third_party/hidapitester/`; link it from a README License section. If the exact source
could not be identified, the fallback was to stop vendoring the binary instead.

Provenance found (details in `third_party/hidapitester/NOTICE.md`):
- the vendored file is byte-identical to the `hidapitester` inside the v0.6 release asset
  `hidapitester-macos-universal.zip`;
- that asset was built and signed by upstream's macOS workflow run 25400702824 at commit
  `171aaf2` (signature timestamp matches the signing step), not at the `v0.6` tag commit
  `9f03f2b`; `hidapitester.c` is identical between the two, only CI files, one Makefile
  packaging line, and a doc differ;
- HIDAPI is tag `hidapi-0.15.0` (`d6b2a97`), pinned by the workflow.

Shipped: `COPYING` (GPL-3.0, identical to gnu.org's text), `NOTICE.md`, HIDAPI's three license
files, and GitHub source tarballs for `171aaf2` and `hidapi-0.15.0` (about 1.06 MB together,
under the 2 MB limit set for this task) with `SHA256SUMS`. A local rebuild from those archives
reported the same versions with the same symbol table and `--help` output.

## Decisions

- The push reliability and fast-path code was already on `main` (57c435b, 7b27844,
  7a26a58); only docs and hygiene were carried over from the local working tree.
- A local `config.json` tuning (`poll_interval_s` 0.5, `absent_polls_required` 4) was NOT
  shipped: `keyboard_watcher` treats a poll gap above 5 x `poll_interval_s` as a sleep/wake
  jump, so halving the interval halves that tolerance to 2.5 s, and a slow `--list` poll can
  then resync to absent and silently skip a real switch. The tracked example stays at the
  defaults (1.0 s, 2 polls). Hunks that would have reverted the earlier scrub (real machine names, a personal
  launchd label) were dropped; the tracked label stays `local.logi_mx_switch`.
- Separate `docs/plans/index.md` not kept: `docs/index.md` is the single index.

## Status log

- 27/09/2026: part 1 implemented, 52 tests passing locally; merged as PR #1 with CI green.
- 27/09/2026: part 2 implemented (third_party/hidapitester/).
