#!/bin/bash
# Build script for Specter-DIY firmware
# Usage: ./tools/build.sh [--flash] [--monitor]
#
# --flash:   Flash firmware after build
# --monitor: Monitor serial output after flash

set -e

REMOTE_HOST="ubuntu@192.168.13.246"
REMOTE_DIR="~/specter-build"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Step 1: Sync local → remote
echo "=== Syncing to remote ==="
rsync -avz --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='*.o' \
    --exclude='*.P' \
    --exclude='*.map' \
    -e "ssh" \
    "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

# Step 2: Build
echo ""
echo "=== Building firmware ==="
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && sudo docker run --rm -v \$PWD:/app -w /app specter24d make disco"

# Step 3: Flash (optional)
if [[ "$1" == "--flash" ]] || [[ "$1" == "-f" ]]; then
    echo ""
    echo "=== Flashing firmware ==="
    ssh "$REMOTE_HOST" "st-flash --connect-under-reset erase && st-flash --connect-under-reset write $REMOTE_DIR/bin/specter-diy.bin 0x08000000"
fi

# Step 4: Monitor (optional)
if [[ "$1" == "--monitor" ]] || [[ "$1" == "-m" ]]; then
    echo ""
    echo "=== Monitoring serial output (Ctrl+C to stop) ==="
    ssh "$REMOTE_HOST" "stty -F /dev/ttyACM0 9600 raw -echo && cat /dev/ttyACM0"
fi

echo ""
echo "=== Done ==="
echo "Firmware: $REMOTE_DIR/bin/specter-diy.bin"
