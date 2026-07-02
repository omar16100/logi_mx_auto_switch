# macOS Port of Logitech-MX-Auto-Switch (02/07/2026)

## Goal
Port https://github.com/aguessous/Logitech-MX-Auto-Switch (Windows PowerShell) to macOS on this Mac mini. When the MX Keys keyboard is Easy-Switched away from this Mac, push the MX Master 3 mouse to the same target channel via HID++ 2.0 ChangeHost (feature 0x1814).

## Hardware found on this Mac (verified 02/07/2026)
- MX Keys: 046D:B35B, Bluetooth LE direct (no Bolt receiver)
- MX Master 3: 046D:B023, Bluetooth LE direct
- Both expose HID++ vendor interface usagePage 0xFF43, usage 0x0202

## Design
- Python 3 stdlib-only watcher (`logi_mx_switch.py`), shells out to `bin/hidapitester` (v0.6 macOS universal, from todbot/hidapitester)
- Poll keyboard presence via HID enumeration each 1s (no TCC permission needed)
- Debounce: N consecutive absent polls before firing (BLE devices blip off/on when idle, observed live)
- Sleep/wake guard: if wall clock jumps more than 5x poll interval, resync state without firing (prevents yanking the mouse back after Mac wakes)
- Send path (needs Input Monitoring permission): open mouse vendor interface, send HID++ long report 0x11 setCurrentHost
- Self-calibrating: discover feature index of 0x1814 at startup via IRoot getFeature, try device index 0xFF then 0x00 (BLE direct vs receiver conventions differ)
- Detailed logging to logs/logi_mx_switch.log
- LaunchAgent plist for auto start at login

## Status
- [x] Hardware probed, vendor interfaces confirmed
- [x] hidapitester v0.6 downloaded, quarantine cleared, runs (arm64)
- [x] Confirmed macOS TCC blocks HID open without Input Monitoring (error 0xE00002E2); enumeration unaffected
- [x] Research done (Solaar + Linux kernel sources): device index 0xFF for BLE-direct HID++ 2.0 (0x00 tolerated), long report 0x11 / 20 bytes is the only BLE option, MX Master 3 B023 has ChangeHost at index 0x0A (still discovered at runtime, firmware-specific), setCurrentHost produces NO reply (BLE link terminates), 0x1815 Hosts Info absent on MX Master 3
- [x] Watcher script + 22 unit tests passing
- [x] Codex review round 1: 7 findings, applied 6 (tri-state presence so transport timeouts never count as keyboard-absent, target_host validation 0..2 without masking, error replies must match device index, OSError handling, case-insensitive TCC detection, multi-read parsing); rejected per-request software id (calls are sequential with a fresh device open each time)
- [x] Success verification: after setCurrentHost, confirm the mouse actually leaves enumeration; skip send if mouse already on target host
- [x] Live test passed: one-shot switch, watch auto-fire, bidirectional round trip verified in both logs 02/07/2026
- [x] Installed as root LaunchDaemon on both Macs (LaunchAgent plan revised: kernel IOHIDFamily requires privileged client for BLE HID open on macOS 26 even after tccd allows; Input Monitoring grants still required for the interpreter + hidapitester identities)
- [x] target_host auto-identified by reading keyboard hosts (0x1815): slot names matched the machines' Bluetooth names; desktop (slot 0) pushes to 1, laptop (slot 1) pushes to 0
- [x] Bug found during live bring-up: parse_read_blocks written against assumed hidapitester output; real format is lowercase mid-line "read N bytes" plus zero-filled buffer on 0-byte reads; fixed with verbatim-output tests (lesson: capture real output before writing parsers)

## Decisions
- hidapitester subprocess instead of python hidapi lib: no brew dependency, same tool as upstream repo, logic stays unit-testable
- Feature index discovered at runtime instead of hardcoding 0x0a from the Windows script: MX Master 3 (B023) table may differ from author's MX Master 3S

## Open questions
- Which channel number is this Mac on, which is the target machine (auto-detect current via 0x1814 getHostInfo once permission granted)
- Other computer needs its own watcher to push the mouse back (original repo if Windows, this port if Mac)
