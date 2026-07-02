# logi_mx_auto_switch

macOS port of [aguessous/Logitech-MX-Auto-Switch](https://github.com/aguessous/Logitech-MX-Auto-Switch) (Windows PowerShell). When an MX Keys keyboard Easy-Switches to another computer, the watcher on the machine it left pushes the MX Master mouse to the same channel, so both devices move together with one key press.

Deployed and verified live on 02/07/2026 across two Macs, switching both directions.

## The problem

Logitech Easy-Switch keys (1/2/3) on the keyboard only switch the keyboard. The mouse must be flipped manually via the button on its underside, or via Logitech software (Flow) that needs to run on both machines and share a network.

## How it works

One watcher instance runs per computer as a root LaunchDaemon. Each instance only pushes the mouse AWAY from its own machine:

1. Poll HID enumeration for the keyboard every second (no permissions needed).
2. Keyboard gone for 2 consecutive polls (debounce against BLE idle blips) means the user pressed Easy-Switch.
3. Open the mouse's HID++ vendor interface (usagePage 0xFF43, usage 0x0202) via the vendored `bin/hidapitester` and send ChangeHost `setCurrentHost(target)` (HID++ 2.0 feature 0x1814).
4. Verify success: the mouse must disappear from this machine's enumeration.

A wall-clock jump guard prevents a false push after Mac sleep/wake, and a transport failure (timeout, missing binary) is treated as "unknown", never as "keyboard absent", so it cannot trigger a false switch.

## Example deployment (author's setup)

| machine | Easy-Switch slot | daemon pushes mouse to |
|---|---|---|
| desktop Mac | 0 (key 1) | host 1 |
| laptop Mac | 1 (key 2) | host 0 |
| third machine | 2 (key 3) | no watcher installed |

Hardware: MX Keys `046D:B35B`, MX Master 3 `046D:B023`, both direct Bluetooth LE (no Bolt/Unifying receiver).

## Commands

```bash
# presence of both devices (no permissions needed)
python3 logi_mx_switch.py status

# the following need root + Input Monitoring grants (see docs/troubleshooting.md)
sudo python3 logi_mx_switch.py discover            # device index, ChangeHost feature index, host info
sudo python3 logi_mx_switch.py switch --target 1   # one-shot push to host 1
sudo python3 logi_mx_switch.py watch               # foreground watcher (daemon runs this)
```

Unit tests (32, no hardware needed):

```bash
uv run --with pytest pytest tests/
```

## Requirements (per machine)

- macOS with the devices paired over Bluetooth
- Input Monitoring grants for the interpreter binary and `bin/hidapitester` (System Settings GUI, cannot be scripted)
- Root: installed as a LaunchDaemon because the kernel requires a privileged client for the HID open, see [docs/troubleshooting.md](docs/troubleshooting.md)

Full install steps: [docs/setup_new_machine.md](docs/setup_new_machine.md)

## Repository layout

```
logi_mx_switch.py            watcher + CLI (stdlib only, unit-testable pure logic)
bin/hidapitester             vendored HID transport CLI (todbot/hidapitester v0.6, macOS universal)
local.logi_mx_switch.plist  LaunchDaemon template (paths are machine-specific)
config.json                  per-machine: target_host etc.
tests/                       pytest suite against verbatim captured device output
docs/                        index, architecture (c4model), HID++ reference, troubleshooting, setup
logs/                        runtime logs (rotating)
```

## Configuration (config.json)

| key | default | meaning |
|---|---|---|
| `target_host` | none (required) | 0-based Easy-Switch slot to push the mouse to |
| `poll_interval_s` | 1.0 | keyboard presence poll period |
| `absent_polls_required` | 2 | consecutive absent polls before firing (debounce) |
| `send_retries` | 8 | push attempts while the mouse is asleep/absent |
| `send_retry_delay_s` | 1.0 | delay between push attempts |
| `keyboard_vidpid` / `mouse_vidpid` | `046D:B35B` / `046D:B023` | change for other MX models |

Transport keys (`hidpp_usage_page` 0xFF43, `hidpp_usage` 0x0202, `hidapitester_path`) also live in `default_config` and rarely need changing.

## Credits

Technique from [aguessous/Logitech-MX-Auto-Switch](https://github.com/aguessous/Logitech-MX-Auto-Switch) (MIT). HID transport by [todbot/hidapitester](https://github.com/todbot/hidapitester). HID++ 2.0 details cross-checked against [Solaar](https://github.com/pwr-Solaar/Solaar), the Linux kernel `hid-logitech-hidpp` driver, and the [logiops wiki](https://github.com/PixlOne/logiops/wiki/HIDPP--2.0).
