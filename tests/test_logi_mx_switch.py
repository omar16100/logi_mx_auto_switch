import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logi_mx_switch import (
    build_hidpp_report,
    report_to_arg,
    parse_read_blocks,
    match_response,
    keyboard_watcher,
    software_id,
    validate_target_host,
    classify_open_output,
    extract_error_lines,
)


class test_build_hidpp_report:
    def test_matches_windows_script_shape(self):
        # Windows original: 0x11,0x00,0x0a,0x1b,0x01,zeros = setCurrentHost(1)
        # with swid 0xb; ours uses swid 0x0D but the same layout
        report = build_hidpp_report(0x00, 0x0A, 0x1, [0x01])
        assert report[0] == 0x11
        assert report[1] == 0x00
        assert report[2] == 0x0A
        assert report[3] == (0x1 << 4) | software_id
        assert report[4] == 0x01
        assert report[5:] == [0x00] * 15
        assert len(report) == 20

    def test_iroot_get_feature(self):
        report = build_hidpp_report(0xFF, 0x00, 0x0, [0x18, 0x14])
        assert report[:6] == [0x11, 0xFF, 0x00, software_id, 0x18, 0x14]

    def test_too_many_params_rejected(self):
        try:
            build_hidpp_report(0xFF, 0x00, 0x0, [0] * 17)
            assert False, "expected ValueError"
        except ValueError:
            pass


class test_report_to_arg:
    def test_format(self):
        assert report_to_arg([0x11, 0xFF, 0x0A]) == "0x11,0xFF,0x0A"


class test_parse_read_blocks:
    def test_real_output_from_device(self):
        # verbatim hidapitester v0.6 output captured live on 02/07/2026
        out = (
            "Opening device, vid/pid:0x046D/0xB023, usagePage/usage: FF43/202\n"
            "Device opened\n"
            "Writing output report of 20-bytes...wrote 20 bytes:\n"
            " 11 FF 00 0D 18 14 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
            "Reading up to 20-byte input report, 2000 msec timeout..."
            "read 20 bytes:\n"
            " 11 FF 00 0D 0A 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
            "Reading up to 20-byte input report, 2000 msec timeout..."
            "read 0 bytes:\n"
            " 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
            "Closing device\n"
        )
        blocks = parse_read_blocks(out)
        assert len(blocks) == 1
        assert blocks[0][:5] == [0x11, 0xFF, 0x00, 0x0D, 0x0A]
        assert len(blocks[0]) == 20

    def test_write_echo_not_parsed_as_read(self):
        out = (
            "Writing output report of 20-bytes...wrote 20 bytes:\n"
            " 11 FF 0A 1D 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
            "Closing device\n"
        )
        assert parse_read_blocks(out) == []

    def test_two_blocks(self):
        out = (
            "...read 20 bytes:\n"
            " 11 FF 05 00 01 00\n"
            "...read 20 bytes:\n"
            " 11 FF 00 0D 0A 03\n"
            "Closing device\n"
        )
        blocks = parse_read_blocks(out)
        assert len(blocks) == 2
        assert blocks[0][2] == 0x05
        assert blocks[1][2] == 0x00

    def test_no_read(self):
        assert parse_read_blocks("Device opened\nClosing device\n") == []

    def test_zero_bytes_read_drops_zero_buffer(self):
        out = (
            "...read 0 bytes:\n"
            " 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n"
            "Closing device\n"
        )
        assert parse_read_blocks(out) == []


class test_classify_open_output:
    # both denial outputs below were captured live on this Mac (02/07/2026)
    def test_not_permitted_denial(self):
        out = (
            "Opening device, vid/pid:0x046D/0xB023, usagePage/usage: FF43/202\n"
            "Error: could not open device at path: DevSrvsID:4301589615\n"
            "Error: hid_open_path: failed to open IOHIDDevice from mach "
            "entry: (0xE00002E2) (iokit/common) not permitted\n"
        )
        assert classify_open_output(out) == "denied"

    def test_privilege_violation_denial(self):
        out = (
            "Opening device, vid/pid:0x046D/0xB023, usagePage/usage: FF43/202\n"
            "Error: could not open device at path: DevSrvsID:4294974283\n"
            "Error: hid_open_path: failed to open IOHIDDevice from mach "
            "entry: (0xE00002C1) (iokit/common) privilege violation\n"
        )
        assert classify_open_output(out) == "denied"

    def test_denial_wins_over_could_not_open(self):
        out = "Error: could not open device\nError: Not Permitted\n"
        assert classify_open_output(out) == "denied"

    def test_absent(self):
        assert classify_open_output(
            "Error: no HID devices found for given vid/pid\n") == "absent"

    def test_no_device_code_is_absent(self):
        assert classify_open_output(
            "Error: open failed: (0xE00002C0) no device\n") == "absent"

    def test_unknown_open_error(self):
        out = (
            "Error: could not open device at path: DevSrvsID:1\n"
            "Error: hid_open_path: (0xE0000345) (iokit/common) mystery\n"
        )
        assert classify_open_output(out) == "open_failed"

    def test_success(self):
        out = "Device opened\nRead 20 bytes:\n 11 FF 00\nClosing device\n"
        assert classify_open_output(out) == "ok"


class test_extract_error_lines:
    def test_joins_error_lines(self):
        out = "Device opening\nError: one\nsomething\nError: two\n"
        assert extract_error_lines(out) == "Error: one | Error: two"

    def test_fallback_without_error_lines(self):
        assert extract_error_lines("weird output\n") == "weird output"


class test_validate_target_host:
    def test_valid(self):
        assert validate_target_host(0) == 0
        assert validate_target_host(2) == 2

    def test_rejects_out_of_range(self):
        for bad in (-1, 3, 255, 300):
            try:
                validate_target_host(bad)
                assert False, f"expected ValueError for {bad}"
            except ValueError:
                pass

    def test_rejects_non_int(self):
        for bad in ("1", 1.0, None, True):
            try:
                validate_target_host(bad)
                assert False, f"expected ValueError for {bad!r}"
            except ValueError:
                pass


class test_match_response:
    def make(self, b):
        return b + [0] * (20 - len(b))

    def test_ok(self):
        fn_sw = (0x0 << 4) | software_id
        resp = self.make([0x11, 0xFF, 0x00, fn_sw, 0x0A, 0x03])
        result = match_response(resp, 0xFF, 0x00, 0x0)
        assert result["kind"] == "ok"
        assert result["params"][0] == 0x0A

    def test_hidpp2_error(self):
        fn_sw = (0x1 << 4) | software_id
        resp = self.make([0x11, 0xFF, 0xFF, 0x0A, fn_sw, 0x02])
        result = match_response(resp, 0xFF, 0x0A, 0x1)
        assert result["kind"] == "error"
        assert result["error_code"] == 0x02

    def test_unrelated_event(self):
        resp = self.make([0x11, 0xFF, 0x05, 0x00, 0x01])
        assert match_response(resp, 0xFF, 0x0A, 0x1)["kind"] == "unrelated"

    def test_empty(self):
        assert match_response([], 0xFF, 0x0A, 0x1)["kind"] == "empty"

    def test_wrong_device_index(self):
        fn_sw = (0x0 << 4) | software_id
        resp = self.make([0x11, 0x00, 0x00, fn_sw, 0x0A])
        assert match_response(resp, 0xFF, 0x00, 0x0)["kind"] == "unrelated"

    def test_error_with_wrong_device_index_is_unrelated(self):
        fn_sw = (0x1 << 4) | software_id
        resp = self.make([0x11, 0x00, 0xFF, 0x0A, fn_sw, 0x02])
        assert match_response(resp, 0xFF, 0x0A, 0x1)["kind"] == "unrelated"


class test_keyboard_watcher:
    def test_fires_after_debounce(self):
        w = keyboard_watcher(1.0, 2)
        t = 0.0
        assert w.feed(True, t) is False  # first poll, learns state
        t += 1
        assert w.feed(True, t) is False
        t += 1
        assert w.feed(False, t) is False  # absent 1/2
        t += 1
        assert w.feed(False, t) is True  # absent 2/2 -> fire
        t += 1
        assert w.feed(False, t) is False  # already fired, no repeat

    def test_blip_does_not_fire(self):
        w = keyboard_watcher(1.0, 2)
        t = 0.0
        w.feed(True, t)
        t += 1
        assert w.feed(False, t) is False  # blip
        t += 1
        assert w.feed(True, t) is False  # back, counter reset
        t += 1
        assert w.feed(False, t) is False  # absent 1/2 again
        t += 1
        assert w.feed(False, t) is True

    def test_starts_absent_never_fires_until_seen_present(self):
        w = keyboard_watcher(1.0, 2)
        t = 0.0
        for _ in range(5):
            assert w.feed(False, t) is False
            t += 1
        w.feed(True, t)
        t += 1
        w.feed(False, t)
        t += 1
        assert w.feed(False, t) is True

    def test_time_jump_resyncs_without_firing(self):
        # Mac slept while keyboard was present, wakes with keyboard absent:
        # must NOT fire (the user long since switched and maybe came back)
        w = keyboard_watcher(1.0, 2)
        t = 0.0
        w.feed(True, t)
        t += 100.0  # sleep/wake gap
        assert w.feed(False, t) is False
        t += 1
        assert w.feed(False, t) is False  # resynced to absent, no firing
        # keyboard returns then leaves again: normal behavior resumes
        t += 1
        w.feed(True, t)
        t += 1
        w.feed(False, t)
        t += 1
        assert w.feed(False, t) is True

    def test_debounce_of_one(self):
        w = keyboard_watcher(1.0, 1)
        t = 0.0
        w.feed(True, t)
        t += 1
        assert w.feed(False, t) is True
