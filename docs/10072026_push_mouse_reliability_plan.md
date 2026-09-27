# Plan: push_mouse reliability (10 Jul 2026) and fast switch path (17 Jul 2026)

Status: **implemented and merged** (commits 57c435b, 7b27844; CHANGELOG 0.1.1 and 0.2.0).
Unit tests: 52 passing (`uv run pytest`). Deploy on each Mac = restart the root daemon
(see Deploy below).

## Context

The daemon pushes the MX Master mouse to follow the MX Keys keyboard on Easy-Switch.
Intermittently the push failed with `mouse absent or unknown in enumeration (attempt
1..8/8)` followed by `giving up pushing the mouse after 8 attempts`, and the mouse did not
follow. Log forensics on the author's machines, a code trace, and an independent code
review found two distinct root causes in the same `push_mouse` path.

## Root causes (10 Jul)

- **Mode A: passive enumeration gate blocked recovery.** `push_mouse` used
  `hidapitester --list` as a hard gate (`if is_present(...) is not True: continue`) and
  never tried the active HID++ path unless `--list` already showed the mouse. An idle
  MX Master drops off HID enumeration (see [troubleshooting.md](troubleshooting.md)), so
  the loop only waited and re-listed until it gave up. `is_present` returning `None`
  (subprocess timeout) collapsed into the same branch as `False` (absent).
- **Mode B: system-sleep false trigger.** A Mac entering sleep drops the keyboard from
  enumeration too, which is indistinguishable from an Easy-Switch, so the trigger fired and
  the retry loop then stalled for minutes across the sleep. The existing time-jump guard
  only resynced the keyboard watcher after the fact and read `time.monotonic()`, which
  macOS pauses across sleep, so it under-detected.

## Changes, part 1: reliability (10 Jul, released as 0.1.1)

1. `push_mouse` no longer gates on passive presence. It always attempts the active
   `discover_device_index` probe; `is_present` is a diagnostic hint only, and `None` vs
   `False` log distinctly.
2. Retry is a wall-clock budget (`send_budget_s`, default 35 s) with backoff
   (`send_backoff_schedule = [0.5, 1, 1, 2, 2, 3, 5, 5, 8]`) instead of a fixed 8 x 1 s.
   The budget limits when an attempt may START; an attempt already in flight at the
   deadline is allowed to finish.
3. Sleep abort: enumeration plus discovery before a send, the send itself, each
   confirmation poll, and each backoff sleep are bracketed; if the wall clock overruns a
   segment's expected duration by more than `sleep_abort_s` (default 30 s) the Mac slept
   mid-push and the push aborts. Two early exits are not bracketed: a failed discovery
   goes straight to the (bracketed) backoff, and the slow path's "already on that host"
   answer returns success before the pre-send check. `now_fn`/`sleep_fn` are injectable
   (default `time.time`/`time.sleep`).
4. The watch loop feeds `time.time()` (wall clock) to `keyboard_watcher.feed` instead of
   `time.monotonic()`, so a sleep is detected and the trigger is suppressed.
5. Deliberately NOT added: a "mouse present at trigger" gate for the whole push. It
   conflicts with Mode A (the mouse is often idle and unlisted at a genuine switch).

New config keys (merged over defaults, so an old `config.json` needs no change):
`send_budget_s`, `sleep_abort_s`. `send_retries` is kept as a legacy key and no longer
bounds the loop; `send_retry_delay_s` now only paces the departure-confirmation poll.

## Changes, part 2: fast switch path (17 Jul, released as 0.2.0)

Every push used to run `discover_device_index` and `get_host_info` (each a `hidpp_call`
that opens the device and waits for replies) before the `setCurrentHost` send, although
the mouse's ChangeHost device index and feature index are stable per device.

1. **Index cache.** `hid_transport.cached_change_host` stores `(device_index,
   feature_index)` after the first successful slow-path discovery. Later pushes skip
   discovery and `getHostInfo` and send `setCurrentHost` directly.
2. **Fast path only when present.** The cache is used only when `is_present` returned
   `True` for this attempt. The slow path proves reachability by opening the device
   before sending; the fast path does not, so a blind send is trusted only when a
   present-then-absent departure can prove it landed. Absent or unknown enumeration falls
   back to full discovery.
3. **Self-healing cache.** A fast-path attempt that completes without confirming a
   departure (send not made, or the mouse still present) clears the cache, so the next
   attempt rediscovers. A sleep abort returns early and leaves the cache as it was.
4. **Real send vs failed open.** `hidpp_call` now reports `opened` (did the HID interface
   open on any attempt). `set_current_host` returns `False` when the device never opened
   (asleep, absent, or permission denied), so a command that was never sent cannot be
   mistaken for a completed switch when the mouse is then absent from enumeration.

## Tests

`tests/test_logi_mx_switch.py` uses a fake transport and an injectable clock (no HID
hardware). Coverage added across both parts: active probe when unlisted (`False`) and
unknown (`None`), distinct log paths, abort on wall-clock jump during backoff, discovery,
send, and confirmation, no attempt starts past the deadline, give up once the budget is spent, invalid
budget fallback, fast path uses the cache and skips discovery, slow path populates the
cache, stale cache invalidation and fallback, send error invalidates the cache, absent
mouse never false-confirms from the cache, fast-path open failure is not a success, and
`set_current_host` open-status handling. Full suite: 52 passing.

## Deploy (per machine, needs root)

The watcher runs as a root LaunchDaemon (label `local.logi_mx_switch`, template
`local.logi_mx_switch.plist`). Restart it to pick up new code:

```
sudo launchctl kickstart -k system/local.logi_mx_switch
# else: sudo launchctl bootout system <plist> && sudo launchctl bootstrap system <plist>
sudo chown -R "$USER" logs/   # logs can become root-owned; restore interactive use
```

Then physically: leave the mouse idle for a while, press Easy-Switch, and expect `mouse
pushed to host` (Mode A); sleep the Mac and confirm no `giving up` error or multi-minute
retry span after wake (Mode B).

## Follow-up (optional, deferred)

IOKit power notifications (pyobjc) for first-class sleep/wake awareness. Cleaner than the
wall-clock heuristic, but a larger change.
