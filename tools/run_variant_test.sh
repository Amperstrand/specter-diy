#!/bin/bash
# run_variant_test.sh - Test a single firmware variant
# Usage: ./run_variant_test.sh <variant_name> [capture_seconds]
#
# This script:
# 1. Flashes the specified variant to the F469-Discovery board
# 2. Captures USB debug output from ttyACM1
# 3. Extracts ATR bytes and result
#
# Prerequisites:
# - st-flash installed
# - Board connected via ST-LINK (miniUSB) and USB (microUSB for debug)
# - Debug output appears on /dev/ttyACM1

set -e

VARIANT="${1:-V7_all}"
CAPTURE_SECONDS="${2:-20}"
BIN_DIR="/home/ubuntu/seedkeeperonly/bin/variants"
DEBUG_PORT="/dev/ttyACM1"
RESULTS_DIR="/home/ubuntu/seedkeeperonly/test_results"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "SeedKeeper Test Matrix - Variant: $VARIANT"
echo "========================================"

# Check binary exists
if [ ! -f "$BIN_DIR/${VARIANT}.bin" ]; then
    echo -e "${RED}ERROR: Binary not found: $BIN_DIR/${VARIANT}.bin${NC}"
    exit 1
fi

# Create results directory
mkdir -p "$RESULTS_DIR"

# Prepare debug port
echo "Preparing debug port..."
sudo stty -F "$DEBUG_PORT" 115200 raw -echo 2>/dev/null || true
sleep 0.5

# Flash the firmware
echo "Flashing $VARIANT..."
sudo st-flash --reset write "$BIN_DIR/${VARIANT}.bin" 0x8000000
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Flash failed${NC}"
    exit 1
fi

# Wait for board to boot
echo "Waiting for boot..."
sleep 2

# Capture debug output
echo "Capturing debug output for ${CAPTURE_SECONDS}s..."
OUTPUT_FILE="$RESULTS_DIR/${VARIANT}_$(date +%Y%m%d_%H%M%S).log"
timeout $CAPTURE_SECONDS sudo cat "$DEBUG_PORT" > "$OUTPUT_FILE" 2>&1 || true

echo "Output saved to: $OUTPUT_FILE"

# Extract results
echo ""
echo "========================================"
echo "RESULTS for $VARIANT:"
echo "========================================"

# Check for ATR
ATR_LINE=$(grep -o '\[BootTrace\]\[SeedKeeper\] ATR:.*' "$OUTPUT_FILE" | head -1)
if [ -n "$ATR_LINE" ]; then
    echo -e "${GREEN}ATR Detected:${NC}"
    echo "  $ATR_LINE"
    
    # Extract ATR bytes
    ATR_BYTES=$(echo "$ATR_LINE" | grep -oE '([0-9A-Fa-f]{2} )+[0-9A-Fa-f]{2}' | head -1)
    echo "  Bytes: $ATR_BYTES"
else
    echo -e "${RED}No ATR detected - card communication failed${NC}"
fi

# Check for keystore error
if grep -q "Keystore error" "$OUTPUT_FILE"; then
    echo -e "${RED}Keystore error detected${NC}"
    grep "Keystore error" "$OUTPUT_FILE"
fi

# Check for successful init
if grep -q "Keystore initialized" "$OUTPUT_FILE"; then
    echo -e "${GREEN}Keystore initialized successfully${NC}"
fi

# Summary
echo ""
echo "--- Summary ---"
if [ -n "$ATR_LINE" ]; then
    echo -e "Status: ${GREEN}PASS${NC} - Smart card detected"
    echo "$VARIANT: PASS" >> "$RESULTS_DIR/summary.txt"
else
    echo -e "Status: ${RED}FAIL${NC} - No smart card response"
    echo "$VARIANT: FAIL" >> "$RESULTS_DIR/summary.txt"
fi

echo ""
echo "Full log: $OUTPUT_FILE"
