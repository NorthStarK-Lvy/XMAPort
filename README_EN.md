# XMAPort

[简体中文](README.md) | English

[![GitHub Release](https://img.shields.io/badge/version-261001.Beta-blue)](../../releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)](#requirements)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](#license)

**XMAPort** is an automated porting tool for Xiaomi HyperOS: feed it the official full-ROM direct links of a source device and a target base ROM, and it automatically handles downloading, unpacking, partition migration, patching and repacking — producing flashable images for the target device.

---

## Introduction

XMAPort is built for the HyperOS porting scene on Xiaomi devices: it migrates one device's HyperOS system partitions (system / system_ext / product / mi_ext, etc.) onto another device's official base ROM, and automatically performs feature syncing, property patching and image repacking.

The whole pipeline is driven by the main script `XMAPort.py` (Python 3.8+, Windows platform). The core migration logic lives in `tools/make_hyper.py` and the packing logic in `tools/pack_partitions.py`. You can run it via an interactive Windows menu, a one-shot CLI mode, or entirely in the cloud using the bundled GitHub Actions workflow.

## Features

- **Fully automated 7-step pipeline**: download → extract recovery ROM → unpack payload → unpack partition images → migrate & patch → repack → collect output, all in one command
- **Parallel dual-ROM download**: source and base ROMs download in parallel with a two-line live progress bar (refreshed every second, showing instant speed) and automatic whole-run retries
- **Fail-fast pipeline**: any failure in download, extraction, migration or packing aborts the run; the summary reflects the real result
- **Full partition migration**: migrates system / system_ext / product / mi_ext onto the target base ROM, with automatic handling of odm / vendor / vbmeta
- **Smart feature syncing**: feature sync, MIUI booster cleanup, APEX sync, refresh-rate / camera / face-unlock sync, build.prop patching
- **MediaTek support**: HWC patches for Dimensity 8100 / 8200
- **Flexible packing**: erofs (with lz4hc / lz4 / zstd compression) or ext4; optional super.img, sparse images, vbmeta verification disabling, and adb debug injection
- **Command executor**: menu [A] can compose a super.img from already-packed partitions
- **Cloud builds**: bundled GitHub Actions workflow lets you build and publish Releases without a local environment

## Workflow

1. **Download ROMs**: source and base ROMs download in parallel via aria2c multi-threaded download of official full-ROM direct links
2. **Extract recovery ROM**: unzip the ROM zip with 7-Zip
3. **Unpack payload**: unpack `payload.bin` / `.dat` with payload-dumper-go
4. **Unpack partition images**: unpack system, vendor, odm and other partition images with simg2img / lpunpack / extract.erofs, etc.
5. **Migrate & patch**: the core logic in `tools/make_hyper.py` migrates the source's system / system_ext / product / mi_ext onto the target base ROM — including feature sync, MIUI booster cleanup, APEX sync, refresh-rate / camera / face-unlock sync, build.prop patches, and HWC patches for MediaTek Dimensity 8100 / 8200
6. **Repack**: `tools/pack_partitions.py` packs partitions as erofs (supporting lz4hc / lz4 / zstd and other compression algorithms) or ext4, with optional super.img generation, sparse images, vbmeta verification disabling and adb debug injection
7. **Collect output**: assembles the final flashable images for the target device

## Requirements

- Windows 10 / 11 64-bit
- Python 3.8+
- About 40GB of free disk space
- Network access to GitHub and Xiaomi CDN

## Usage

### Option 1: Interactive menu (Windows)

Run the main script and follow the menu:

```bat
python XMAPort.py
```

Besides one-click porting, the main menu offers **[A] Command Executor** (1 = compose a super.img from existing partition images in `workspace/packed`; insufficient space shows a hint instead of auto-retrying), **[C] Open-Source Credits** and **[D] Clean workspace**.

### Option 2: One-shot CLI mode

```bat
python XMAPort.py --auto --device <target-codename> --source <source-rom-url> --target <base-rom-url>
```

Example:

```bat
python XMAPort.py --auto --device sky --source https://.../source-rom-full.zip --target https://.../target-rom-full.zip
```

- `--device`: target device codename (letters, digits, underscore and hyphen only)
- `--source`: direct URL of the source device's full ROM (must not start with `ultimateota`; **leave empty to use a local archive, or reuse the previous workspace if none exists**)
- `--target`: direct URL of the target base ROM (must not start with `ultimateota`; leave empty as above)

> Note: before running, check `config.ini` as described in [Configuration](#configuration) — especially `device_platform` and `device_size`.

### Option 3: GitHub Actions cloud build

The repository ships with `.github/workflows/build.yml` — no local environment needed:

1. Open the repo's **Actions** page and select the **build** workflow
2. Click **Run workflow** (`workflow_dispatch`), and fill in:
   - `device`: target device codename
   - `source`: direct URL of the source full ROM
   - `target`: direct URL of the base full ROM
3. When the build finishes, `super.img` is automatically split into volumes and published to a Release

In addition, every push automatically packs the source code and publishes an `XMAPort-*-Beta` release.

## Configuration

All settings live in `config.ini` (GBK/ANSI encoding):

### Essential settings (must verify)

| Key | Description |
| --- | --- |
| `device_platform` | Device platform: `Qualcomm` / `MTK`. **Must be filled in truthfully — a wrong value risks a hard brick.** |
| `device_size` | Total size of the target device's super partition in bytes; default `6979321856` (6.5GB). **Must match your actual device.** |

### Download settings

Put the source / base ROM direct links under `[source]` / `[target]` — **leave a URL empty to skip downloading and use local archives in the corresponding download directory; reuse the previous workspace only if no local archive exists**. `[settings]` controls aria2c's `threads`, `max-connection` (hard limit 16 in official aria2), `timeout` and whole-run `retry` (`0` = single attempt, no retries).

For local packages, place the source full recovery ROM in `workspace/download_source/` and the target base ROM in `workspace/download_target/`, clear the corresponding `url`, and run normally. Each side can independently use a local package or a URL. A local download directory must contain exactly one archive; multiple archives cause an error instead of being merged. Online downloads use a stable URL-derived filename and only that archive is extracted; other downloaded files are retained.

A side supplied with an archive rebuilds its ROM and payload directories. A side with neither a URL nor a local archive reuses existing partition images, or extracts them from the existing ROM directory if insufficient. Failed/interrupted extraction leaves an `.incomplete` marker; provide an archive to rebuild before reusing that side.

Before migration, both filesystem trees are freshly extracted from the selected images, removing previous patches and generated permission/SELinux metadata. **Manual edits in those filesystem trees are discarded.** Only `config/fs_special.conf` and `config/fc_special.conf` custom rules are retained on each side. Downloads, project configuration, device configuration and historical logs are retained. Cleanup failures abort the workflow. Menu `[D]` still deletes only the listed images, payloads and device configuration, rather than resetting the entire workspace.

### Packing settings (`[packing]`)

| Key | Description |
| --- | --- |
| `format` | `erofs` or `ext4` |
| `compression` / `compression_level` | erofs compression algorithm and level (e.g. `lz4hc` + `8`) |
| `pack_super` | Whether to pack a super.img; when `false`, compose one via menu [A] |
| `sparse` | Whether to output sparse-format images |
| `metadata_size` / `metadata_slots` | super metadata size and slot count (defaults `65536` / `3` recommended) |
| `virtual_ab` | Whether Virtual A/B is enabled |
| `super_name` / `super_group` | super partition name and dynamic-partition group (`qti_dynamic_partitions` on Qualcomm, `main` on MTK) |
| `enable_adb_debug` | Whether to inject adb debug (debugging only; keep off for daily builds) |
| `patch_vbmeta` | Whether to disable vbmeta verification |
| `is_skip_apex` | Skip system_ext repacking and copy the source image directly |
| `erofs_old_kernel` | Legacy-kernel compress layout (old-kernel devices only) |
| `utc_stamp` | Image timestamp; leave empty for automatic UTC |

### build.prop patch list

The prop list below the `; patch build prop list` marker line is written into build.prop during migration — e.g. fast charging (`persist.vendor.accelerate.charge`), night charging (`persist.vendor.night.charge`), default refresh rate (`ro.vendor.display.default_fps`), and so on. You may add your own props, but **custom props are not guaranteed to boot**.

## Notes & FAQ

- **ROM direct links**: `--source` / `--target` must be direct download URLs of official full recovery ROMs (fastboot packages are not supported), and must not start with `ultimateota`
- **Wrong platform can brick your device**: double-check whether the target is Qualcomm or MediaTek before setting `device_platform`
- **super size must be accurate**: a `device_size` that doesn't match the device may make the image unflashable or unbootable
- **Disk space**: downloads, unpacking and repacking produce many intermediate files — reserve about 40GB
- **Antivirus false positives**: the bundled third-party executables (aria2c, 7z, mkfs.erofs, etc.) may be flagged; add trust exclusions or temporarily disable your antivirus
- **Theoretical support**: Xiaomi 11–15, REDMI K50–K90, Note / REDMI 12–15 series (see the table below for what has actually been tested)
- **Finding the device codename**: the codename is the device identifier in the base ROM's version string (e.g. `sky` in `OS2.0.204.0.VMWCNXM`)

## Tested Ports

| Source device | Target device |
| --- | --- |
| REDMI Note12R | K70 / Note12Turbo / Note17 / Xiaomi 12 / Xiaomi 17 Ultra |
| Note12T Pro | K90 Max |
| K100 Pro | Xiaomi 17 Ultra |

These are the verified routes. Other devices with matching architectures may work in theory but are unverified — test at your own risk.

## Disclaimer

- This project is **for personal learning and testing only**; please delete the related files within 24 hours of downloading
- Flashing carries risks of **bricking** and **data loss**. You assume full responsibility for any consequences of using this project
- This project is **not affiliated with Xiaomi**; the ROMs are copyrighted by Xiaomi Inc.
- **Commercial use is prohibited**

## License

- The project's main code (`XMAPort.py`, `tools/*.py`) is licensed under [MIT](LICENSE)
- The bundled third-party tools are governed by their original licenses respectively: AGPL-3.0 / GPL-2.0 / LGPL-2.1, with the corresponding LICENSE files included in the repository

## Acknowledgements

- This project is built with AI-assisted coding (Vibe Coding, using DeepSeek / GLM / Xiaomi MiMo, etc.)
- Thanks to the following open-source projects:
  - [aria2](https://github.com/aria2/aria2), [7-Zip](https://www.7-zip.org/)
  - [payload-dumper-go](https://github.com/ssut/payload-dumper-go)
  - [erofs-utils](https://github.com/erofs/erofs-utils), [lpunpack / lpmake](https://android.googlesource.com/platform/system/extras/), [e2fsprogs](https://github.com/tytso/e2fsprogs)
  - [Google Brotli](https://github.com/google/brotli)
  - [Magisk](https://github.com/topjohnwu/Magisk) (the vbmeta verification-disable method references its verified approach)
  - And all developers in the HyperOS porting community
