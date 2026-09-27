# c4 model: logi_mx_auto_switch

## L1 context
Person at desk switches MX Keys keyboard between computers with Easy-Switch keys. This system makes the MX Master 3 mouse follow automatically. One watcher instance runs per computer; each instance only pushes the mouse AWAY from its own machine when the keyboard leaves.

## L2 containers
- watcher (this repo, per Mac): Python 3 stdlib process, root LaunchDaemon local.logi_mx_switch (/Library/LaunchDaemons), interpreter = uv-managed CPython (stable TCC identity). Deployed on two Macs (slot 0 and slot 1), each pushing the mouse to the other.
- hidapitester (vendored binary, bin/): HID transport CLI, spawned per operation. Third-party, GPL-3.0 (todbot/hidapitester v0.6, HIDAPI 0.15.0); license, provenance, and exact source archives in third_party/hidapitester/
- macOS IOKit HID stack: enumeration (permission free); device open requires BOTH a TCC Input Monitoring grant (system settings, for the responsible interpreter binary and hidapitester) AND a privileged (root) client: kernel IOHIDFamily gates BLE HID devices with keyboard usages beyond TCC on macOS 26 (verified in unified log)
- Logitech devices: MX Keys 046D:B35B (presence signal; hosts named via feature 0x1815), MX Master 3 046D:B023 (receives HID++ ChangeHost 0x1814 at feature index 0x0A, device index 0xFF, vendor interface usagePage 0xFF43 usage 0x0202, BLE direct)

## L3 components (logi_mx_switch.py)
- pure logic: build_hidpp_report, report_to_arg, parse_read_blocks, match_response, classify_open_output, keyboard_watcher (debounce + sleep/wake time-jump guard). Unit tested, no hardware.
- hid_transport: subprocess wrapper around hidapitester; is_present via enumeration (tri-state, None = unknown), send_and_read via open+send+read returning (status, responses) with status denied on TCC/kernel refusal; cached_change_host holds the last known-good (device_index, feature_index) for the fast path
- hidpp ops: hidpp_call (send, read, match, retry; reports `opened` = did the HID interface open), discover_device_index (IRoot getFeature 0x1814, tries device index 0xFF then 0x00), get_host_info (fn 0), set_current_host (fn 1; returns False when the device never opened, so an unsent command is never read as a switch)
- push_mouse: always attempts the active HID++ path (enumeration is a diagnostic hint, not a gate), retries with backoff until the wall-clock budget send_budget_s is spent (no new attempt starts past it; one in flight may finish), aborts when a blocking segment overruns by more than sleep_abort_s (the Mac slept mid-push), and uses the cached indices only when the mouse is present at that attempt
- commands: watch (main loop), discover, switch, status

## data flow (switch event)
keyboard absent N consecutive polls (wall-clock time-jump guard suppresses sleep/wake triggers) -> push_mouse -> per attempt: is_present(mouse) as a hint -> fast path (cached indices, mouse present) or slow path (discover indexes + getHostInfo, then cache them) -> setCurrentHost(target_host) -> confirm the mouse left enumeration -> done; otherwise drop a stale cache, back off, and start another attempt while send_budget_s is not yet spent. Config from config.json merged over default_config (target_host required for watch).

## dev and CI
- tests/test_logi_mx_switch.py: pure-logic tests on verbatim captured hidapitester output plus a fake transport and injectable clock for push_mouse; no HID access.
- .github/workflows/ci.yml: ubuntu runner, astral-sh/setup-uv, `uv run --locked pytest` on pushes and pull requests to main.

## change log
- 02/07/2026: initial macOS port (watch/discover/switch/status, debounce, sleep/wake guard).
- 15/07/2026: push_mouse reliability (active probe always, wall-clock budget with backoff, sleep abort). See [10072026_push_mouse_reliability_plan.md](10072026_push_mouse_reliability_plan.md).
- 17/07/2026: fast switch path (cached ChangeHost indices, hidpp_call `opened` tracking).
- 27/09/2026: CI workflow added; pytest moved to a uv dev dependency group. See [27092026_ci_and_license_hygiene_plan.md](27092026_ci_and_license_hygiene_plan.md).
- 27/09/2026: third_party/hidapitester/ added (GPL-3.0 text, notice, HIDAPI notices, exact source for the vendored binary).
