# Setup on a new machine

Adds the watcher to another Mac (e.g. to cover the third Easy-Switch slot). Windows machines should use the upstream repo's PowerShell scripts instead.

## 1. Pair and identify

Pair the MX Keys and MX Master with the new Mac over Bluetooth on a free Easy-Switch slot. Copy the project:

```bash
rsync -a --exclude .venv --exclude logs --exclude .git --exclude config.json \
  ~/projects/logi_mx_auto_switch/ <user>@<host>:projects/logi_mx_auto_switch/
```

Confirm the devices enumerate (works with zero permissions, devices must be actively connected to THIS machine):

```bash
bin/hidapitester --list | grep -i 046d
```

Other MX models have different Bluetooth PIDs; adjust `keyboard_vidpid` / `mouse_vidpid` in config.json if yours differ from B35B/B023.

## 2. Pick a stable interpreter

Use a fixed real python3 binary path, NOT `/usr/bin/python3` (Xcode shim, unstable TCC identity). uv-managed CPython works well:

```bash
ls ~/.local/share/uv/python/   # e.g. cpython-3.12.13-macos-aarch64-none/bin/python3.12
```

The script is stdlib-only, python 3.9+.

## 3. Grant Input Monitoring (GUI only, cannot be scripted)

System Settings > Privacy & Security > Input Monitoring: add BOTH binaries and enable their toggles:

- `<project>/bin/hidapitester`
- the interpreter chosen in step 2

Tips: the file picker hides /opt and dotted paths; use Cmd+Shift+G to type the path, or reveal in Finder (`open -R <path>`) and drag the file into the list. For a headless Mac, stage remotely via ssh (`open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"` and `open -R ...` run inside the GUI session) and finish over Screen Sharing.

## 4. Configure

`config.json`: set `target_host` to the 0-based slot of the machine the mouse should FOLLOW THE KEYBOARD TO when it leaves this one. `discover` (below) shows the mouse's CURRENT slot; slot NAMES require the keyboard HostsInfo probes in docs/hidpp_reference.md.

`local.logi_mx_switch.plist`: fix all absolute paths (interpreter, script, logs) for this machine's username.

## 5. Verify before installing

```bash
sudo /path/to/python3 logi_mx_switch.py discover            # expect feature index + host info
sudo /path/to/python3 logi_mx_switch.py switch --target N   # one-shot: mouse must hop away
```

Preconditions for the switch test: target machine awake, mouse's bottom Easy-Switch button within reach as the recovery path.

## 6. Install the daemon

```bash
sudo cp local.logi_mx_switch.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/local.logi_mx_switch.plist
sudo chmod 644 /Library/LaunchDaemons/local.logi_mx_switch.plist
sudo launchctl bootout system/local.logi_mx_switch 2>/dev/null
sudo launchctl bootstrap system /Library/LaunchDaemons/local.logi_mx_switch.plist
```

Must be a root LaunchDaemon, not a user LaunchAgent: the kernel requires a privileged client for the HID open (docs/troubleshooting.md). Verify:

```bash
sudo launchctl print system/local.logi_mx_switch | grep -E "state|pid"
tail -2 logs/logi_mx_switch.log   # expect "watching keyboard ..."
```

## 7. End-to-end test

Press the keyboard's Easy-Switch key for another machine: the mouse should follow (typically ~4 s observed; retries can take longer if the mouse is asleep) and the log must show `keyboard left this Mac` then `confirmed gone from this Mac`. Repeat in the other direction from the other machine's watcher.
