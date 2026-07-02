# todo

## done (02/07/2026) - COMPLETE, verified live both directions
- [x] cloned upstream repo, analyzed Windows PowerShell scripts
- [x] probed hardware: MX Keys 046D:B35B, MX Master 3 046D:B023, both BLE direct, HID++ vendor interface 0xFF43/0x0202
- [x] hidapitester v0.6 macOS universal in bin/
- [x] logi_mx_switch.py: watch/discover/switch/status, runtime feature discovery, debounce, sleep/wake guard
- [x] codex review round 1 (code) + round 2 (plan) + round 3 (TCC issue) applied
- [x] TCC findings: enumeration free; HID open needs Input Monitoring grant AND root (kernel IOHIDFamily privilegedClient gate on macOS 26, TCC allow alone insufficient, verified via unified log)
- [x] parser fix: hidapitester prints lowercase mid-line "read N bytes" and zero-filled buffers for 0-byte reads; tests now use verbatim captured output
- [x] 32 unit tests passing (uv run --with pytest pytest tests/)
- [x] hosts identified via keyboard 0x1815 friendly names (slots map to machines' Bluetooth names)
- [x] root LaunchDaemon installed on both Macs (slot 0: target_host 1, slot 1: target_host 0)
- [x] live verified: one-shot switch, watch auto-fire, full bidirectional round trip (logs both sides)

## deferred
- [ ] third pairing (slot 2) has no watcher; switching to it needs manual mouse switch back
- [ ] verify daemons after next reboot of each Mac (RunAtLoad set, expected fine)
