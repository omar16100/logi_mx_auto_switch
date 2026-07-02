# c4 model: logi_mx_auto_switch

## L1 context
Person at desk switches MX Keys keyboard between computers with Easy-Switch keys. This system makes the MX Master 3 mouse follow automatically. One watcher instance runs per computer; each instance only pushes the mouse AWAY from its own machine when the keyboard leaves.

## L2 containers
- watcher (this repo, per Mac): Python 3 stdlib process, root LaunchDaemon local.logi_mx_switch (/Library/LaunchDaemons), interpreter = uv-managed CPython (stable TCC identity). Deployed on two Macs (slot 0 and slot 1), each pushing the mouse to the other.
- hidapitester (vendored binary, bin/): HID transport CLI, spawned per operation
- macOS IOKit HID stack: enumeration (permission free); device open requires BOTH a TCC Input Monitoring grant (system settings, for the responsible interpreter binary and hidapitester) AND a privileged (root) client: kernel IOHIDFamily gates BLE HID devices with keyboard usages beyond TCC on macOS 26 (verified in unified log)
- Logitech devices: MX Keys 046D:B35B (presence signal; hosts named via feature 0x1815), MX Master 3 046D:B023 (receives HID++ ChangeHost 0x1814 at feature index 0x0A, device index 0xFF, vendor interface usagePage 0xFF43 usage 0x0202, BLE direct)

## L3 components (logi_mx_switch.py)
- pure logic: build_hidpp_report, report_to_arg, parse_read_blocks, match_response, classify_open_output, keyboard_watcher (debounce + sleep/wake time-jump guard). Unit tested, no hardware.
- hid_transport: subprocess wrapper around hidapitester; is_present via enumeration (tri-state, None = unknown), send_and_read via open+send+read returning (status, responses) with status denied on TCC/kernel refusal
- hidpp ops: hidpp_call (send, read, match, retry), discover_device_index (IRoot getFeature 0x1814, tries device index 0xFF then 0x00), get_host_info (fn 0), set_current_host (fn 1)
- commands: watch (main loop), discover, switch, status

## data flow (switch event)
keyboard absent N consecutive polls -> push_mouse -> wait mouse enumerable -> discover indexes -> setCurrentHost(target_host) -> mouse hops channel. Config from config.json (target_host required for watch).
