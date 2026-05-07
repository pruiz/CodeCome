#!/usr/bin/env bash
# CodeCome nested-virt smoke test. Marker: __TARGET_NAME__.
# This is intentionally a placeholder. Replace with the actual QEMU
# invocation for the target firmware / image / payload.
set -euo pipefail

docker compose -f sandbox/docker-compose.yml run --rm codecome-sandbox bash -lc '
set -euo pipefail

cd /workspace

echo "CodeCome nested-virt placeholder test"
echo "Replace this script with target-specific QEMU runs for __TARGET_NAME__."

# Example skeletons (commented out):
#
# qemu-system-__QEMU_ARCH__ \
#   -M virt -nographic -no-reboot \
#   -kernel src/kernel.bin \
#   -append "console=ttyAMA0" \
#   -monitor none -serial mon:stdio
#
# qemu-system-__QEMU_ARCH__ \
#   -drive file=src/image.qcow2,if=virtio,format=qcow2 \
#   -m 512 -nographic
true
'
