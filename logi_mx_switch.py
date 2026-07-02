#!/usr/bin/env python3
"""
logi_mx_switch: macOS port of Logitech-MX-Auto-Switch.

Watches the MX Keys keyboard via HID enumeration. When the keyboard leaves this
Mac (Easy-Switch pressed), sends HID++ 2.0 ChangeHost (feature 0x1814) to the
MX Master mouse so it follows to the same target channel.

Uses bin/hidapitester (todbot/hidapitester) as the HID transport.
Enumeration needs no macOS permission. Opening a device to send the switch
command requires Input Monitoring permission for the responsible process.

Commands:
  watch                run the watcher loop (default)
  discover             probe mouse: device index, 0x1814 feature index, host info
  switch --target N    one-shot: push mouse to host channel N (0-based) now
  status               show keyboard/mouse presence
"""

import argparse
import json
import logging
import logging.handlers
import re
import subprocess
import sys
import time
from pathlib import Path

project_dir = Path(__file__).resolve().parent
default_config_path = project_dir / "config.json"
log_dir = project_dir / "logs"

hidpp_long_report_id = 0x11
hidpp_long_len = 20
iroot_feature_index = 0x00
feature_change_host = 0x1814
software_id = 0x0D  # arbitrary nonzero nibble to match responses to our calls
hidpp2_error_marker = 0xFF

default_config = {
    "keyboard_vidpid": "046D:B35B",
    "mouse_vidpid": "046D:B023",
    "hidpp_usage_page": "0xFF43",
    "hidpp_usage": "0x0202",
    "target_host": None,  # 0-based Easy-Switch channel of the OTHER computer
    "poll_interval_s": 1.0,
    "absent_polls_required": 2,  # debounce: BLE devices blip off/on when idle
    "send_retries": 8,
    "send_retry_delay_s": 1.0,
    "hidapitester_path": str(project_dir / "bin" / "hidapitester"),
}

log = logging.getLogger("logi_mx_switch")


def setup_logging(verbose: bool) -> None:
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fileh = logging.handlers.RotatingFileHandler(
        log_dir / "logi_mx_switch.log", maxBytes=1_000_000, backupCount=3
    )
    fileh.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.addHandler(fileh)
    log.addHandler(console)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


def load_config(path: Path) -> dict:
    config = dict(default_config)
    if path.exists():
        with open(path) as f:
            config.update(json.load(f))
        log.debug("loaded config from %s", path)
    else:
        log.info("no config file at %s, using defaults", path)
    return config


# ---------------------------------------------------------------------------
# pure logic: HID++ report building and parsing (unit tested, no hardware)
# ---------------------------------------------------------------------------

def build_hidpp_report(device_index: int, feature_index: int, function_id: int,
                       params: list) -> list:
    """20-byte HID++ 2.0 long report as a list of ints."""
    if len(params) > hidpp_long_len - 4:
        raise ValueError(f"too many params: {len(params)}")
    report = [
        hidpp_long_report_id,
        device_index,
        feature_index,
        ((function_id & 0x0F) << 4) | software_id,
    ] + list(params)
    report += [0x00] * (hidpp_long_len - len(report))
    return report


def report_to_arg(report: list) -> str:
    """Format report bytes for hidapitester --send-output."""
    return ",".join(f"0x{b:02X}" for b in report)


def parse_read_blocks(hidapitester_output: str) -> list:
    """Extract every read block from hidapitester output as a list of byte
    lists. Real output format (captured live): the marker is lowercase and
    embedded mid-line ('Reading up to 20-byte input report, 2000 msec
    timeout...read 20 bytes:'), and a 'read 0 bytes' still prints an
    all-zeros buffer line, which must be dropped."""
    blocks = []
    current = None
    for line in hidapitester_output.splitlines():
        marker = re.search(r"read (\d+) bytes", line, re.IGNORECASE)
        if marker:
            if current:
                blocks.append(current)
            # a zero-length read prints a zero-filled buffer: skip it
            current = [] if int(marker.group(1)) > 0 else None
            continue
        if current is not None:
            tokens = line.strip().split()
            if tokens and all(re.fullmatch(r"[0-9A-Fa-f]{1,2}", t) for t in tokens):
                current.extend(int(t, 16) for t in tokens)
            elif current:
                blocks.append(current)
                current = None
    if current:
        blocks.append(current)
    return blocks


# TCC denial signatures observed live on this Mac plus SDK-header variants:
# 0xE00002E2 = kIOReturnNotPermitted ("not permitted"),
# 0xE00002C1 = kIOReturnNotPrivileged ("privilege violation")
tcc_denial_markers = ("not permitted", "0xe00002e2", "privilege violation",
                      "0xe00002c1", "not privileged", "not authorized")
# absence-like: device really not there (0xE00002C0 = kIOReturnNoDevice)
absence_markers = ("no hid devices found", "0xe00002c0")


def classify_open_output(output: str) -> str:
    """Classify hidapitester output after an --open attempt.
    'denied' = macOS Input Monitoring/TCC denial (fatal, retry pointless),
    'absent' = device not enumerable (asleep/away, retry can help),
    'open_failed' = open failed for an unrecognized reason (log raw error),
    'ok' = open succeeded. Denial is checked first: denial output also
    contains 'could not open'."""
    low = output.lower()
    if any(marker in low for marker in tcc_denial_markers):
        return "denied"
    if any(marker in low for marker in absence_markers):
        return "absent"
    if "could not open" in low:
        return "open_failed"
    return "ok"


def extract_error_lines(output: str) -> str:
    """The raw hidapitester error lines, for logging unknown failures."""
    lines = [line.strip() for line in output.splitlines()
             if "error" in line.lower()]
    return " | ".join(lines) if lines else output.strip()[:200]


def validate_target_host(value) -> int:
    """target_host must be an exact int in 0..2 (Easy-Switch has 3 channels).
    Raises ValueError otherwise; no silent masking."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"target_host must be an integer, got {value!r}")
    if not 0 <= value <= 2:
        raise ValueError(f"target_host must be 0, 1 or 2 (0-based), got {value}")
    return value


def match_response(response: list, device_index: int, feature_index: int,
                   function_id: int) -> dict:
    """Classify a HID++ response to our call.
    Returns {kind: ok|error|unrelated|empty, params, error_code}."""
    if not response:
        return {"kind": "empty", "params": [], "error_code": None}
    if len(response) < 5 or response[0] != hidpp_long_report_id:
        return {"kind": "unrelated", "params": [], "error_code": None}
    fn_sw = ((function_id & 0x0F) << 4) | software_id
    # HID++ 2.0 error: byte2 = 0xFF, then echoed feature index, fn/sw, err code
    if (response[1] == device_index and response[2] == hidpp2_error_marker
            and response[3] == feature_index and response[4] == fn_sw
            and len(response) >= 6):
        return {"kind": "error", "params": [], "error_code": response[5]}
    if response[1] == device_index and response[2] == feature_index \
            and response[3] == fn_sw:
        return {"kind": "ok", "params": response[4:], "error_code": None}
    return {"kind": "unrelated", "params": [], "error_code": None}


class keyboard_watcher:
    """Debounced present/absent state machine with a sleep/wake guard.

    feed(present, now) returns True exactly when the switch should fire:
    keyboard was present, then absent for absent_polls_required consecutive
    polls. A wall-clock jump larger than time_jump_factor * poll interval
    (Mac slept, process paused) resyncs state without firing.
    """

    time_jump_factor = 5

    def __init__(self, poll_interval_s: float, absent_polls_required: int):
        self.poll_interval_s = poll_interval_s
        self.absent_polls_required = max(1, absent_polls_required)
        self.was_present = None  # unknown until first poll
        self.absent_count = 0
        self.last_poll_time = None

    def feed(self, present: bool, now: float) -> bool:
        jumped = (self.last_poll_time is not None
                  and now - self.last_poll_time
                  > self.time_jump_factor * self.poll_interval_s)
        self.last_poll_time = now
        if jumped:
            log.info("time jump detected (sleep/wake), resyncing state to "
                     "present=%s without firing", present)
            self.was_present = present
            self.absent_count = 0
            return False
        if self.was_present is None:
            self.was_present = present
            return False
        if present:
            self.was_present = True
            self.absent_count = 0
            return False
        if not self.was_present:
            return False  # already gone, already handled
        self.absent_count += 1
        if self.absent_count < self.absent_polls_required:
            return False
        self.was_present = False
        self.absent_count = 0
        return True


# ---------------------------------------------------------------------------
# hidapitester transport
# ---------------------------------------------------------------------------

class hid_transport:
    def __init__(self, config: dict):
        self.exe = config["hidapitester_path"]
        self.usage_page = config["hidpp_usage_page"]
        self.usage = config["hidpp_usage"]

    def _run(self, args: list, timeout_s: float = 10.0):
        """Run hidapitester. Returns combined output, or None when the
        transport itself failed (timeout, missing binary): callers must treat
        None as UNKNOWN, never as device-absent."""
        cmd = [self.exe] + args
        log.debug("run: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout_s)
        except subprocess.TimeoutExpired:
            log.warning("hidapitester timed out: %s", " ".join(args))
            return None
        except OSError as exc:
            log.error("cannot run hidapitester at %s: %s", self.exe, exc)
            return None
        out = proc.stdout + proc.stderr
        log.debug("hidapitester exit=%s output=%r", proc.returncode, out)
        return out

    def is_present(self, vidpid: str):
        """True/False when enumeration answered, None when the transport
        failed (unknown, must not be treated as absent)."""
        out = self._run(["--vidpid", vidpid, "--list"], timeout_s=8.0)
        if out is None:
            return None
        return vidpid.replace(":", "/").upper() in out.upper()

    def send_and_read(self, vidpid: str, report: list,
                      read_timeout_ms: int = 2000, reads: int = 1):
        """Open the HID++ vendor interface, send one long report, read up to
        `reads` responses. Returns (status, responses):
        status 'ok' | 'denied' (macOS Input Monitoring, fatal) | 'failed'
        (device absent/asleep or transport failure), responses = list of
        byte lists."""
        args = [
            "--vidpid", vidpid,
            "--usagePage", self.usage_page,
            "--usage", self.usage,
            "--open",
            "--length", str(hidpp_long_len),
            "--send-output", report_to_arg(report),
            "--timeout", str(read_timeout_ms),
        ]
        args += ["--read-input"] * max(1, reads)
        args += ["--close"]
        out = self._run(args, timeout_s=(read_timeout_ms / 1000) * reads + 8.0)
        if out is None:
            return "failed", []
        kind = classify_open_output(out)
        if kind == "denied":
            log.error("macOS denied HID open (Input Monitoring permission "
                      "missing for the responsible app). Grant it in System "
                      "Settings > Privacy & Security > Input Monitoring. "
                      "Raw error: %s", extract_error_lines(out))
            return "denied", []
        if kind == "absent":
            log.warning("could not open %s (device absent or asleep)", vidpid)
            return "failed", []
        if kind == "open_failed":
            log.warning("HID open failed for %s: %s", vidpid,
                        extract_error_lines(out))
            return "failed", []
        return "ok", parse_read_blocks(out)


# ---------------------------------------------------------------------------
# HID++ operations
# ---------------------------------------------------------------------------

def hidpp_call(transport: hid_transport, vidpid: str, device_index: int,
               feature_index: int, function_id: int, params: list,
               attempts: int = 3, read_timeout_ms: int = 2000,
               reads: int = 1) -> dict:
    """Send a HID++ call, read one or more reports, and match ours among
    possible unsolicited events. Only resent (attempts > 1) for idempotent
    calls like IRoot getFeature and getHostInfo."""
    report = build_hidpp_report(device_index, feature_index, function_id, params)
    for attempt in range(attempts):
        status, responses = transport.send_and_read(vidpid, report,
                                                    read_timeout_ms, reads)
        if status == "denied":
            return {"kind": "denied", "params": [], "error_code": None}
        for response in responses:
            result = match_response(response, device_index, feature_index,
                                    function_id)
            if result["kind"] in ("ok", "error"):
                return result
            log.debug("attempt %d: %s report %s", attempt + 1,
                      result["kind"], response)
        time.sleep(0.3)
    return {"kind": "empty", "params": [], "error_code": None}


def discover_device_index(transport: hid_transport, vidpid: str):
    """BLE-direct devices usually answer on device index 0xFF, receiver
    setups on 0x00-0x06. Try 0xFF then 0x00; return the one that answers
    IRoot getFeature(0x1814) together with the feature index."""
    feat_msb, feat_lsb = feature_change_host >> 8, feature_change_host & 0xFF
    for device_index in (0xFF, 0x00):
        result = hidpp_call(transport, vidpid, device_index,
                            iroot_feature_index, 0x0, [feat_msb, feat_lsb],
                            reads=2)
        if result["kind"] == "denied":
            return "denied", None
        if result["kind"] == "ok" and result["params"]:
            feature_index = result["params"][0]
            if feature_index == 0:
                log.warning("device index 0x%02X: feature 0x1814 not supported",
                            device_index)
                continue
            log.info("device index 0x%02X answers; ChangeHost feature index "
                     "= 0x%02X", device_index, feature_index)
            return device_index, feature_index
        log.debug("device index 0x%02X: %s", device_index, result["kind"])
    return None, None


def get_host_info(transport: hid_transport, vidpid: str, device_index: int,
                  feature_index: int):
    """ChangeHost getHostInfo (function 0): returns (nb_hosts, current_host)."""
    result = hidpp_call(transport, vidpid, device_index, feature_index, 0x0,
                        [], reads=2)
    if result["kind"] == "ok" and len(result["params"]) >= 2:
        return result["params"][0], result["params"][1]
    log.warning("getHostInfo failed: %s error=%s", result["kind"],
                result["error_code"])
    return None, None


def set_current_host(transport: hid_transport, vidpid: str, device_index: int,
                     feature_index: int, target_host: int) -> bool:
    """ChangeHost setCurrentHost (function 1). On success the BLE link
    terminates immediately and no reply arrives (per Solaar), so read with a
    short timeout only to catch an HID++ error reply (e.g. invalid host)."""
    result = hidpp_call(transport, vidpid, device_index, feature_index, 0x1,
                        [target_host], attempts=1, read_timeout_ms=400)
    if result["kind"] == "error":
        log.error("setCurrentHost rejected, HID++ error code %s",
                  result["error_code"])
        return False
    log.info("setCurrentHost(%d) sent (response kind: %s)", target_host,
             result["kind"])
    return True


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_status(transport: hid_transport, config: dict) -> int:
    for name, vidpid in (("keyboard", config["keyboard_vidpid"]),
                         ("mouse", config["mouse_vidpid"])):
        present = transport.is_present(vidpid)
        state = "unknown" if present is None else ("present" if present
                                                   else "absent")
        log.info("%s %s: %s", name, vidpid, state)
    return 0


def cmd_discover(transport: hid_transport, config: dict) -> int:
    vidpid = config["mouse_vidpid"]
    if transport.is_present(vidpid) is not True:
        log.error("mouse %s not present, move it to wake it and retry", vidpid)
        return 1
    device_index, feature_index = discover_device_index(transport, vidpid)
    if device_index == "denied" or device_index is None:
        log.error("could not talk HID++ to the mouse. If the log above shows "
                  "a permission denial, grant Input Monitoring first.")
        return 1
    nb_hosts, current_host = get_host_info(transport, vidpid, device_index,
                                           feature_index)
    log.info("mouse: device_index=0x%02X change_host_feature_index=0x%02X "
             "nb_hosts=%s current_host=%s (0-based)", device_index,
             feature_index, nb_hosts, current_host)
    if nb_hosts == 2 and current_host is not None and config.get("target_host") is None:
        suggested = 1 - current_host
        log.info("exactly 2 hosts paired: suggested target_host = %d", suggested)
    return 0


def push_mouse(transport: hid_transport, config: dict, target_host: int) -> bool:
    """Full push sequence with retries: wait for mouse to be reachable,
    discover indexes, send setCurrentHost."""
    vidpid = config["mouse_vidpid"]
    for attempt in range(config["send_retries"]):
        if transport.is_present(vidpid) is not True:
            log.warning("mouse absent or unknown in enumeration "
                        "(attempt %d/%d)", attempt + 1, config["send_retries"])
            time.sleep(config["send_retry_delay_s"])
            continue
        device_index, feature_index = discover_device_index(transport, vidpid)
        if device_index == "denied":
            log.error("aborting: cannot send without Input Monitoring "
                      "permission")
            return False
        if device_index is None:
            time.sleep(config["send_retry_delay_s"])
            continue
        nb_hosts, current_host = get_host_info(transport, vidpid, device_index,
                                               feature_index)
        if current_host == target_host:
            log.info("mouse already on host channel %d, nothing to do",
                     target_host)
            return True
        if nb_hosts is not None and target_host >= nb_hosts:
            log.error("target_host %d is out of range: mouse reports only "
                      "%d paired hosts", target_host, nb_hosts)
            return False
        if set_current_host(transport, vidpid, device_index, feature_index,
                            target_host):
            # success means the mouse leaves this Mac: verify by enumeration
            # (None = unknown must not count as a confirmed departure)
            for _ in range(3):
                time.sleep(1.0)
                if transport.is_present(vidpid) is False:
                    log.info("mouse pushed to host channel %d (confirmed "
                             "gone from this Mac)", target_host)
                    return True
            log.warning("mouse still present after setCurrentHost(%d), "
                        "retrying (already on that host, or send lost)",
                        target_host)
        time.sleep(config["send_retry_delay_s"])
    log.error("giving up pushing the mouse after %d attempts",
              config["send_retries"])
    return False


def cmd_switch(transport: hid_transport, config: dict, target_host: int) -> int:
    return 0 if push_mouse(transport, config, target_host) else 1


def cmd_watch(transport: hid_transport, config: dict) -> int:
    target_host = config.get("target_host")
    if target_host is None:
        log.error("target_host is not set in config.json. Run 'discover' to "
                  "see the current channel, then set target_host to the other "
                  "computer's channel (0-based).")
        return 1
    try:
        target_host = validate_target_host(target_host)
    except ValueError as exc:
        log.error("invalid config: %s", exc)
        return 1
    keyboard = config["keyboard_vidpid"]
    watcher = keyboard_watcher(config["poll_interval_s"],
                               config["absent_polls_required"])
    log.info("watching keyboard %s, will push mouse %s to host %d on "
             "disconnect (poll %.1fs, debounce %d polls)", keyboard,
             config["mouse_vidpid"], target_host, config["poll_interval_s"],
             config["absent_polls_required"])
    while True:
        present = transport.is_present(keyboard)
        if present is None:
            # transport failure: unknown state must never count as absent
            log.warning("keyboard presence unknown this poll, skipping")
        elif watcher.feed(present, time.monotonic()):
            log.info("keyboard left this Mac, pushing mouse to host %d",
                     target_host)
            push_mouse(transport, config, target_host)
        time.sleep(config["poll_interval_s"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="watch",
                        choices=["watch", "discover", "switch", "status"])
    parser.add_argument("--target", type=int, default=None,
                        help="0-based host channel for 'switch'")
    parser.add_argument("--config", type=Path, default=default_config_path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    config = load_config(args.config)
    if not Path(config["hidapitester_path"]).is_file():
        log.error("hidapitester not found at %s, cannot start",
                  config["hidapitester_path"])
        return 2
    transport = hid_transport(config)

    if args.command == "status":
        return cmd_status(transport, config)
    if args.command == "discover":
        return cmd_discover(transport, config)
    if args.command == "switch":
        target = args.target if args.target is not None else config.get("target_host")
        if target is None:
            log.error("no target: pass --target N or set target_host in config")
            return 1
        try:
            target = validate_target_host(target)
        except ValueError as exc:
            log.error("%s", exc)
            return 1
        return cmd_switch(transport, config, target)
    return cmd_watch(transport, config)


if __name__ == "__main__":
    sys.exit(main())
