# GitHub Upload Checklist

This repository contains the source and reproducibility material for the
mROS2-ESP32 QoS hardware-validation project. It is not a release bundle.

## Do Not Commit Local Files

The following files are intentionally local-only:

```text
platform/wifi/wifi_secrets.h
platform/rtps/config_local.h
build/
results/
workspace/*/build/
outputs/
mROS2-QoS-p4-run/
upstream_bench/mros2-esp32/
microros_bench/micro_ros_espidf_component/
microros_bench/agent_toolchain/
*.ppt*
*.zip
*.opju
*.xlsx
*.pcapng
*.inspect.ndjson
```

Use `git status --ignored --short` if you need to confirm they are ignored.

## Repository Shape

The upload repository is intentionally source-first and flattened.
`mros2/` and `mros2/embeddedRTPS/` are normal source directories here, not git submodules.

That makes the repository easier to open and inspect on GitHub.
No `git submodule update` step is required after cloning this upload repository.

Commit and push from the repository root:

```bash
git status
git add .
git commit -m "Add ESP32 QoS hardware validation"
git push -u origin main
```

## Quick Public-Safety Check

Before pushing, run:

```bash
git status --short --ignored
grep -RInE "<local-ip-fragment>|<local-user-home>|<known-password-fragment>" \
  --exclude-dir=.git --exclude-dir=build --exclude-dir=results .
```

The real WiFi password and local WSL IP must only appear in ignored local files.

Before committing, verify that no presentation files are tracked:

```bash
git ls-files | grep -Ei '\.(ppt|pptx|pptm)$' && exit 1 || true
git status --short --ignored
```
