# Troubleshooting

All findings verified live on macOS 26 (Darwin 25/26 kernels), 02/07/2026.

## The two-gate permission model

Opening a BLE HID device that exposes keyboard usages (both the MX Keys AND the MX Master 3, which carries a keyboard usage collection) requires passing BOTH gates:

1. TCC Input Monitoring (`kTCCServiceListenEvent`): tccd checks the RESPONSIBLE process identity plus the requesting binary. Grants are GUI-only (System Settings > Privacy & Security > Input Monitoring); CLI tools get silently denied without any prompt.
2. Kernel IOHIDFamily privilege: even after tccd allows, `IOHIDLibUserClient` requires a privileged (root/euid 0) client for these devices. Log signature: `IOHIDLibUserClient ... Entitlements 0 privilegedClient : No` then `open client not privileged`.

Consequence: the watcher must run as ROOT (LaunchDaemon in /Library/LaunchDaemons) AND the interpreter + hidapitester still need Input Monitoring grants. Plain HID enumeration (`--list`, presence polling) needs neither.

## Error signature decoder (hid_open failures)

| raw error | constant | meaning here |
|---|---|---|
| `(0xE00002E2) not permitted` | kIOReturnNotPermitted | TCC denial (no grant for the responsible identity) |
| `(0xE00002C1) privilege violation` | kIOReturnNotPrivileged | TCC passed but caller is not root (kernel gate), or stale-cached TCC denial |
| `(0xE00002C0)` | kIOReturnNoDevice | device genuinely absent/asleep |

`classify_open_output()` in logi_mx_switch.py maps all denial variants to `denied` and logs raw error lines for anything unknown.

## TCC attribution: who actually needs the grant

- Processes under a tmux server: the tmux binary is the responsible process. The RUNNING server caches its denial; a grant only takes effect after `tmux kill-server` (kills all sessions). Granting the calling binary does not help while the responsible process stays cached.
- launchd jobs: the job's ProgramArguments[0] is the responsible process for itself and children. Do NOT use `/usr/bin/python3` (Xcode shim, target moves with xcode-select and Xcode updates, breaking the grant silently). This project pins the uv-managed CPython real path.
- `sudo launchctl submit` lands the job in the USER domain (euid 501), not the system domain. For a true root context use a plist in /Library/LaunchDaemons plus `sudo launchctl bootstrap system ...`.

## Debug recipes

Watch the actual TCC decision (use the full path, zsh shadows `log` with a builtin):

```bash
/usr/bin/log show --last 5m --info --predicate 'process == "tccd"' \
  | grep -E "ListenEvent|hidapitester|python"
# look for: ReqResult(Auth Right: Allowed (System Set)) vs a denial
```

Watch the kernel gate:

```bash
/usr/bin/log show --last 5m --info \
  --predicate 'senderImagePath CONTAINS "IOHIDFamily"' | grep -i privileg
```

Daemon status and logs:

```bash
sudo launchctl print system/local.logi_mx_switch | grep -E "state|pid"
tail -f logs/logi_mx_switch.log
```

## Behavioral notes

- BLE devices blip off HID enumeration when idle and re-register (registry IDs change). This is why `absent_polls_required` exists; a single absent poll never fires. For the same reason `push_mouse` treats `--list` as a hint only and always attempts the active HID++ path, retrying with backoff within `send_budget_s` rather than giving up when the idle mouse is momentarily unlisted. ("mouse not listed in enumeration ... attempting active probe anyway" and "mouse enumeration unknown (transport timeout) ..." are the two distinct diagnostic paths for `--list` returning absent vs. timing out.)
- "time jump detected" in the log is the sleep/wake guard resyncing state without firing. The watcher polls on the wall clock (`time.time`), not `time.monotonic`, because macOS pauses the monotonic clock across sleep so only the wall clock reveals the gap. It also triggers after a push blocks the poll loop for a few seconds; both cases are benign by design.
- "wall-clock jumped Ns ... the Mac slept mid-push, aborting" means a push was in flight when the machine slept (the mouse is unreachable while asleep). The push aborts rather than exhausting attempts across the sleep; the next real Easy-Switch pushes normally.
- setCurrentHost success = the mouse VANISHES from enumeration (the BLE link drops). "mouse still present after setCurrentHost" means it was already on that host or the send was lost; the watcher retries.
- After running commands via sudo, log files under logs/ may become root-owned; `sudo chown -R <user> logs/` restores interactive use.

## Uninstall (per machine)

```bash
sudo launchctl bootout system/local.logi_mx_switch
sudo rm /Library/LaunchDaemons/local.logi_mx_switch.plist
# then remove the two Input Monitoring entries in System Settings
```
