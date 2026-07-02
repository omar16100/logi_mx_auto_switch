---
name: logi-mx-auto-switch
description: Use when working in this repo on the Logitech MX auto-switch watcher; when the mouse fails to follow the keyboard; when hidapitester or IOHIDDeviceOpen fails with 0xE00002E2 not permitted, 0xE00002C1 privilege violation, or "device absent or asleep"; when installing the watcher on a new Mac; or when probing Logitech HID++ devices (ChangeHost, HostsInfo, feature indexes).
---

# logi-mx-auto-switch operations

Watcher that pushes a Logitech MX mouse to the Easy-Switch channel the MX Keys keyboard just moved to. One root LaunchDaemon per Mac; each only pushes the mouse AWAY from its own machine.

## Non-negotiables (verified on macOS 26, cost hours to learn)

1. Opening these BLE HID devices needs BOTH TCC Input Monitoring grants (interpreter binary + bin/hidapitester, GUI-only) AND root. tccd allowing is not enough; the kernel separately requires a privileged client. Never conclude one grant "should" suffice; check `docs/troubleshooting.md` decoder first.
2. `0xE00002E2` and `0xE00002C1` are both permission denials, not device problems. Only `no HID devices found` / `0xE00002C0` mean the device is really absent.
3. HID enumeration (presence polling, `--list`) needs no permissions at all.
4. hidapitester output: read marker is lowercase mid-line (`...read 20 bytes:`); a 0-byte read still prints a zero-filled buffer. Parse with `parse_read_blocks`, never a hand-rolled grep.
5. Feature indexes are firmware-specific; resolve via IRoot getFeature at runtime (the code does). setCurrentHost gets NO reply; success = device vanishes from enumeration.
6. A transport failure (timeout, missing binary) must be treated as UNKNOWN presence, never as keyboard-absent; treating it as absent falsely yanks the mouse.

## Quick reference

| task | command |
|---|---|
| device presence (no perms) | `python3 logi_mx_switch.py status` |
| probe mouse + host info | `sudo /path/to/python3 logi_mx_switch.py discover` |
| one-shot push | `sudo /path/to/python3 logi_mx_switch.py switch --target N` |
| daemon status | `sudo launchctl print system/local.logi_mx_switch \| grep -E "state\|pid"` |
| runtime log | `tail -f logs/logi_mx_switch.log` |
| tests (no hardware) | `uv run --with pytest pytest tests/` |
| TCC decision trace | `/usr/bin/log show --last 5m --info --predicate 'process == "tccd"'` (full path: zsh shadows `log`) |

## Docs map

- `docs/troubleshooting.md`: permission model, error decoder, tccd/IOHID log recipes, uninstall
- `docs/setup_new_machine.md`: install runbook (grants, plist paths, daemon bootstrap, live test)
- `docs/hidpp_reference.md`: HID++ message layout, IRoot/0x1814/0x1815, verbatim captures, probe one-liners
- `docs/c4model.md`: architecture source of truth; update it for any architecture change

## Editing rules

- Pure logic (report building/parsing, debounce state machine) stays subprocess-free and unit-tested; add tests using verbatim captured device output, never assumed formats.
- The live switch test physically moves the user's mouse to another machine; get explicit go-ahead and ensure the mouse's bottom Easy-Switch button is reachable before running it.
