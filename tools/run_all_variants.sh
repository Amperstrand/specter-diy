#!/bin/bash
# run_all_variants.sh - Run all 8 firmware variants for the test matrix
# Usage: ./run_all_variants.sh
#
# This runs all variants in order, with power cycle reminders between tests.
# IMPORTANT: Power cycle the board between variants (unplug/replug both USB cables)
#            because USART configuration persists across resets.

set -e

RESULTS_DIR="/home/ubuntu/seedkeeperonly/test_results"

# All 8 variants in test order
VARIANTS=(
    "V0_baseline"      # No fixes - expected FAIL
    "V7_all"           # All fixes - expected PASS (sanity check)
    "V1_pps"           # PPS only
    "V2_t1reconfig"    # T1_RECONFIG only
    "V3_halfduplex"    # HALFDUPLEX only
    "V4_t1_pps"        # T1_RECONFIG + PPS
    "V5_hd_pps"        # HALFDUPLEX + PPS
    "V6_hd_t1"         # HALFDUPLEX + T1_RECONFIG
)

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================"
echo "SeedKeeper Test Matrix - All Variants"
echo "========================================"
echo ""
echo "IMPORTANT: Power cycle the board between variants!"
echo "Unplug both USB cables, wait 2 seconds, replug."
echo ""
echo "Test matrix:"
echo "  V0: No fixes (baseline) - expected FAIL"
echo "  V7: All fixes - expected PASS (sanity check)"
echo "  V1-V6: Unknown outcomes"
echo ""

# Clear previous results
rm -f "$RESULTS_DIR/summary.txt"
mkdir -p "$RESULTS_DIR"

read -p "Press Enter to start testing..."

for variant in "${VARIANTS[@]}"; do
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Testing: $variant${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    # Run the test
    ./tools/run_variant_test.sh "$variant" 20
    
    # Power cycle reminder (except after last variant)
    if [ "$variant" != "V6_hd_t1" ]; then
        echo ""
        echo -e "${YELLOW}>>> POWER CYCLE REQUIRED <<<${NC}"
        echo "Unplug both USB cables from the board."
        echo "Wait 2 seconds."
        echo "Replug both USB cables."
        echo ""
        read -p "Press Enter after power cycle to continue to next variant..."
    fi
done

echo ""
echo "========================================"
echo "ALL TESTS COMPLETE"
echo "========================================"
echo ""
echo "Summary:"
cat "$RESULTS_DIR/summary.txt"
echo ""
echo "Individual logs available in: $RESULTS_DIR/"
