# HID++ 2.0 reference (as verified on this hardware)

Everything below was verified live on 02/07/2026 against MX Keys (046D:B35B) and MX Master 3 (046D:B023), both connected via direct Bluetooth LE on macOS 26. Byte dumps are verbatim captures.

## Transport

- Vendor HID interface: usagePage `0xFF43`, usage `0x0202` (Bluetooth-direct devices; receivers use 0xFF00/0x0002 instead).
- Only LONG reports exist over BLE: report ID `0x11`, 20 bytes total (1 ID + 19 payload). The short 7-byte `0x10` report is not in the BLE report map.
- Device index byte: `0xFF` for BLE-direct HID++ 2.0 devices (Solaar and the Linux kernel convention). This hardware also answers on `0x00`; the code tries `0xFF` first, then `0x00`.

## Message layout

```
byte 0: 0x11 (long report ID)
byte 1: device index (0xFF)
byte 2: feature INDEX (position in the device's feature table, not the feature ID)
byte 3: (functionId << 4) | softwareId    softwareId: any nonzero nibble, echoed back
byte 4+: parameters
```

Error reply: `0x11 <devidx> 0xFF <featureIndex> <fnSw> <errorCode> ...` (byte 2 = 0xFF marks the error).

## IRoot (feature index 0x00): resolving feature indexes

Feature indexes are firmware-specific (an MX Anywhere 3S was reported at 0x0B where these are 0x0A), so resolve at runtime.

getFeature(featId), function 0. Request params: featId MSB, LSB. Response params: featureIndex, flags, version.

```
sent: 11 FF 00 0D 18 14 00 ...            ask for feature 0x1814
read: 11 FF 00 0D 0A 00 01 00 ...         index 0x0A, flags 0, version 1
```

featureIndex 0 in the response means the feature is unsupported.

## ChangeHost 0x1814 (MX Master 3: index 0x0A, verified)

The keyboard's ChangeHost index was never probed here (its 0x0A slot is occupied by HostsInfo, so ChangeHost is elsewhere in its table); resolve via IRoot before use.

- Function 0 getHostInfo: no params. Response params: nbHosts, currentHost (0-based). This mouse reports nbHosts=3 regardless of how many slots are actually paired.
  ```
  sent: 11 FF 0A 0D 00 ...
  read: 11 FF 0A 0D 03 00 ...              3 hosts, currently host 0
  ```
- Function 1 setCurrentHost: param byte 0 = target host (0-based). NO reply on success: the BLE link terminates immediately. Use a short read timeout only to catch an error reply; confirm success by the device leaving HID enumeration.

## HostsInfo 0x1815 (MX Keys: index 0x0A; ABSENT on MX Master 3)

Lets you identify which physical machine is on which slot by name.

- Function 0 getHostsInfo: params begin `13 04 03 00`: bytes 0-1 capability bytes, byte 2 nbHosts=3, byte 3 currentHost=0.
- Function 1 getHostInfo(host): response params: hostIndex, status (1 = paired), busType, numPages, nameLen, maxNameLen.
  ```
  read: 11 FF 0A 1D 01 01 04 04 0C 18 ...   host 1 paired, name is 12 bytes
  ```
- Function 3 getHostFriendlyName(host, byteOffset): response params: hostIndex, offset, then up to 14 name bytes (UTF-8). Chunk with offset for names longer than 14 bytes.
  ```
  read: 11 FF 0A 3D 01 00 <up to 14 UTF-8 name bytes> ...   zero-padded
  ```

The returned names match each machine's Bluetooth name, so slots can be mapped to physical computers definitively. Names can contain multi-byte UTF-8 (a curly apostrophe is 3 bytes: `E2 80 99`), so nameLen counts bytes, not glyphs.

## hidapitester output quirks (parser contract)

- The read marker is lowercase and mid-line: `Reading up to 20-byte input report, 2000 msec timeout...read 20 bytes:`.
- A 0-byte read still prints a zero-filled 20-byte buffer line, which must be discarded.
- The write echo line (`...wrote 20 bytes:`) is followed by a hex line that must not be parsed as a response.
- `--send-output` first byte is the report ID. `--timeout` applies per `--read-input`, and multiple `--read-input` flags are allowed in one invocation.

## One-liner probes (root required, see troubleshooting)

```bash
# where is ChangeHost on this device?
sudo bin/hidapitester --vidpid 046D:B023 --usagePage 0xFF43 --usage 0x0202 \
  --open --length 20 --timeout 3000 \
  --send-output 0x11,0xFF,0x00,0x0D,0x18,0x14,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 \
  --read-input
```
