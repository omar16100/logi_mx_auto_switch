# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-17

### Added

- **Fast switch path.** The mouse's HID++ ChangeHost indices (device index +
  feature index) are cached after the first successful discovery, so subsequent
  switches skip the ~8 s `discover` + `getHostInfo` round-trips and send
  `setCurrentHost` directly. A warm push drops from ~10 s to ~1-2 s when the mouse
  is awake. A stale cache self-heals: a cached send that is not confirmed clears
  the cache and falls back to a full rediscovery within the same attempt budget.

### Changed

- `setCurrentHost` now distinguishes a real send from a failed device open. The
  HID++ layer tracks whether the mouse's interface actually opened, so an asleep,
  absent, or permission-denied mouse returns a failure instead of being mistaken
  for a completed switch. The fast path is taken only when the mouse is present at
  the trigger, so a confirmed present-then-absent departure genuinely proves the
  switch landed.

## [0.1.1] - 2026-07-15

### Fixed

- Idle-mouse switches no longer give up prematurely. `push_mouse` always attempts
  the active HID++ path instead of gating on the passive `--list` enumeration
  (which drops an idle Bluetooth-LE mouse), retrying with backoff inside a
  wall-clock budget rather than a fixed retry count.
- System sleep no longer causes false pushes or minutes-long stuck retries. The
  watch loop uses the wall clock (`time.time`), which advances across macOS sleep
  unlike `time.monotonic`, to detect sleep and suppress a false trigger; and
  `push_mouse` aborts if a step overruns so it cannot grind across a sleep or act
  on stale device state.
- `is_present` transport timeouts are logged distinctly from a genuinely absent
  mouse.

## [0.1.0] - 2026-07-02

### Added

- Initial release. A per-machine root LaunchDaemon watches the MX Keys keyboard
  via HID enumeration and pushes the MX Master mouse to the same Easy-Switch host
  (HID++ 2.0 ChangeHost, feature 0x1814) when the keyboard leaves, using a vendored
  `hidapitester` transport. Pure HID++ report building/parsing is unit-tested.

[0.2.0]: https://github.com/omar16100/logi_mx_auto_switch/compare/57c435b...main
[0.1.1]: https://github.com/omar16100/logi_mx_auto_switch/compare/ffe7df6...57c435b
[0.1.0]: https://github.com/omar16100/logi_mx_auto_switch/commit/ffe7df6
