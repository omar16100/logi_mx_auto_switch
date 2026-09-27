# hidapitester: third-party notice

`bin/hidapitester` is a prebuilt copy of **hidapitester** by Tod E. Kurt
(<https://github.com/todbot/hidapitester>), licensed under the **GNU General Public License,
version 3** (full text: [COPYING](COPYING)). It is compiled together with **HIDAPI**
(<https://github.com/libusb/hidapi>), whose license notices are reproduced below.

`logi_mx_switch.py` runs `bin/hidapitester` as a separate program (subprocess). The rest of this
repository is under the MIT license in [../../LICENSE](../../LICENSE); hidapitester is distributed
here under its own GPL-3.0 license, and nothing in this repository changes its terms.

## The binary

| field | value |
|---|---|
| path | `bin/hidapitester` |
| format | Mach-O universal binary (x86_64, arm64), 194064 bytes |
| sha256 | `0ef2e469e19962e493b85baa3e40770c6d3b18089852f880ae06b43a349747dc` |
| `--version` | `hidapitester version: v0.6`, `hidapi version: 0.15.0` |
| upstream release | [v0.6](https://github.com/todbot/hidapitester/releases/tag/v0.6), asset `hidapitester-macos-universal.zip` (sha256 `9f0d547eb1f0e0960d8939f63953c839f6f2168e7741d84dd33ab2acd182e2e0`) |
| code signature | Developer ID Application: ThingM Corporation (25Z4SKT2U5), timestamp 2026-05-05 20:32:28 UTC |

The vendored file is byte-identical to the `hidapitester` inside that release asset (checked
27 Sep 2026 with `cmp` and sha256; the zip's sha256 equals the digest GitHub lists for the asset).

## Exact corresponding source

The v0.6 release binary was produced by upstream's GitHub Actions workflow
`.github/workflows/macos.yml`, run
[25400702824](https://github.com/todbot/hidapitester/actions/runs/25400702824) (job
74499185506), which built:

| component | ref | commit |
|---|---|---|
| hidapitester | `main` at the time of the run | `171aaf2fe4e687faa280810e83fd8fee5af0b0bd` ("fix macos workflow codesign", 2026-05-05) |
| HIDAPI | tag `hidapi-0.15.0` (pinned by the workflow's `HIDAPI_VERSION: "0.15.0"`) | `d6b2a974608dec3b76fb1e36c189f22b9cf3650c` |

How the build was identified: that run's signing step ran 20:32:27 to 20:32:28 UTC, which matches
the binary's signature timestamp and the file time inside the release zip. The two earlier runs
that had a signing step (commits `401816c`, `c1127e3`) failed at their certificate-import or
signing steps before anything was packaged, and the builds before them had no signing step at all.

Relation to the `v0.6` tag (`9f03f2b9c37da9d1be0e72d25f4a9745caf9c37b`): `hidapitester.c` is
identical. Between the tag and `171aaf2` only CI workflow files changed, the Makefile gained one
line (`ARCH=universal`, which only renames the packaged zip), and `docs/codesigning-macos.md` was
removed.

Source archives for exactly those two commits (GitHub-generated tarballs) are in
[source/](source/), with checksums in [source/SHA256SUMS](source/SHA256SUMS):

- `source/hidapitester-171aaf2fe4e687faa280810e83fd8fee5af0b0bd.tar.gz`, from
  <https://github.com/todbot/hidapitester/archive/171aaf2fe4e687faa280810e83fd8fee5af0b0bd.tar.gz>
- `source/hidapi-hidapi-0.15.0.tar.gz`, from
  <https://github.com/libusb/hidapi/archive/refs/tags/hidapi-0.15.0.tar.gz>

The hidapitester archive includes its `Makefile`, `CMakeLists.txt`, and the
`.github/workflows/macos.yml` that drove the release build.

## Building from this source

Needs macOS with the Xcode command line tools. The Makefile expects HIDAPI in a sibling
directory named `hidapi`, and derives the version string from `git tag`, which an archive does
not have, so pass it explicitly:

```bash
cd third_party/hidapitester   # from the repository root
mkdir build && cd build
tar -xzf ../source/hidapitester-171aaf2fe4e687faa280810e83fd8fee5af0b0bd.tar.gz
tar -xzf ../source/hidapi-hidapi-0.15.0.tar.gz
mv hidapitester-171aaf2fe4e687faa280810e83fd8fee5af0b0bd hidapitester
mv hidapi-hidapi-0.15.0 hidapi
cd hidapitester
make GIT_TAG_RAW=v0.6
./hidapitester --version   # hidapitester version: v0.6 / hidapi version: 0.15.0
```

Upstream's workflow then signs the binary with its Developer ID and notarizes the zip. A local
build is not byte-identical (different SDK, no Developer ID signature). A local build made this
way on 27 Sep 2026 reported the same versions and had the same symbol table (`nm`, both
architectures) and the same `--help` output as the vendored binary.

## HIDAPI license notice

HIDAPI (Copyright 2009, Alan Ott, Signal 11 Software, and contributors) can be used under one of
three licenses, at the user's choice: the GNU GPL v3, a BSD-style license, or the original HIDAPI
license. The notices shipped with HIDAPI 0.15.0 are reproduced here:

- [hidapi-LICENSE.txt](hidapi-LICENSE.txt): the three-license statement
- [hidapi-LICENSE-bsd.txt](hidapi-LICENSE-bsd.txt): BSD-style license
- [hidapi-LICENSE-orig.txt](hidapi-LICENSE-orig.txt): original HIDAPI license
- GPL v3: the same license terms as [COPYING](COPYING); HIDAPI's own copy is `LICENSE-gpl3.txt` inside the HIDAPI archive (it differs from COPYING only in a few URLs, e.g. http vs https)

## Replacing the binary

If `bin/hidapitester` is ever replaced, update this notice and replace the archives in
`source/` with the exact commits that built the new binary, or remove the binary and document a
separate install instead.
