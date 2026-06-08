# Local ZMK build (Docker)

## Prerequisites

- Docker Desktop running
- Qube in bootloader mode mounts as `/Volumes/NRF52BOOT`

## Quick flash

```bash
cd ~/zmk/ergohaven-zmk-config
./scripts/flash-qube-ruen.sh
```

1. Edit `config/velvet_v3_ui_ruen.keymap` (or other config files)
2. Double-tap reset on qube so `NRF52BOOT` appears in Finder
3. Run the script above

The script builds `velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2` and copies it to the bootloader volume.

## Build only

```bash
./scripts/flash-qube-ruen.sh --build-only
```

Output: `build/artifacts/velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2`

## Other targets

```bash
./scripts/zmk-docker-build.sh \
  --shield "velvet_v3_ui_right raw_hid_adapter" \
  --keymap velvet_v3_ui_ruen \
  --artifact velvet_v3_ui_right_ruen-ergohaven-zmk
```

## First run

The first build downloads the ZMK/Zephyr toolchain inside Docker and can take 15–30 minutes. Later builds reuse `.zmk-workspace/`.

Force refresh modules:

```bash
./scripts/zmk-docker-build.sh --refresh
```
