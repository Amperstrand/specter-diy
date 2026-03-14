#!/bin/bash
# validate_pins.sh - Validate pin configuration consistency
# Run this before building to catch configuration mismatches
#
# Usage: ./scripts/validate_pins.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD_DIR="$SCRIPT_DIR/../f469-disco/micropython/ports/stm32/boards/STM32F469DISC"

ERRORS=0
WARNINGS=0

echo "=== Pin Configuration Validation ==="
echo ""

# Check if required files exist
if [ ! -f "$BOARD_DIR/mpconfigboard.h" ]; then
    echo "❌ ERROR: mpconfigboard.h not found at $BOARD_DIR/mpconfigboard.h"
    exit 1
fi

if [ ! -f "$BOARD_DIR/pins.csv" ]; then
    echo "❌ ERROR: pins.csv not found at $BOARD_DIR/pins.csv"
    exit 1
fi

echo "Checking UART3 configuration..."

# Verify mpconfigboard.h has correct UART3 pins
if grep -q "MICROPY_HW_UART3_TX.*pin_B10" "$BOARD_DIR/mpconfigboard.h"; then
    echo "  ✅ UART3_TX = pin_B10 (correct)"
else
    echo "  ❌ ERROR: UART3_TX should be pin_B10 in mpconfigboard.h"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "MICROPY_HW_UART3_RX.*pin_B11" "$BOARD_DIR/mpconfigboard.h"; then
    echo "  ✅ UART3_RX = pin_B11 (correct)"
else
    echo "  ❌ ERROR: UART3_RX should be pin_B11 in mpconfigboard.h"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "Checking pins.csv labels..."

# Verify pins.csv has correct UART3 labels (not misleading UART1)
if grep -q "^UART3_TX,PB10$" "$BOARD_DIR/pins.csv"; then
    echo "  ✅ pins.csv: UART3_TX,PB10 (correct)"
else
    if grep -q "^UART1_TX,PB10$" "$BOARD_DIR/pins.csv"; then
        echo "  ⚠️  WARNING: pins.csv has UART1_TX,PB10 (should be UART3_TX,PB10)"
        echo "     This is misleading - PB10 only supports USART3, not USART1"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "  ❓ INFO: pins.csv does not have UART3_TX,PB10 entry"
    fi
fi

if grep -q "^UART3_RX,PB11$" "$BOARD_DIR/pins.csv"; then
    echo "  ✅ pins.csv: UART3_RX,PB11 (correct)"
else
    if grep -q "^UART1_RX,PB11$" "$BOARD_DIR/pins.csv"; then
        echo "  ⚠️  WARNING: pins.csv has UART1_RX,PB11 (should be UART3_RX,PB11)"
        echo "     This is misleading - PB11 only supports USART3, not USART1"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "  ❓ INFO: pins.csv does not have UART3_RX,PB11 entry"
    fi
fi

echo ""
echo "Checking for PD8/PD9 UART references (common mistake)..."

# Warn if anyone tries to use PD8/PD9 for UART3 (they're FMC pins)
if grep -q "UART.*PD8" "$BOARD_DIR/mpconfigboard.h" 2>/dev/null; then
    echo "  ⚠️  WARNING: PD8 referenced for UART - this is an FMC SDRAM pin!"
    WARNINGS=$((WARNINGS + 1))
fi

if grep -q "UART.*PD9" "$BOARD_DIR/mpconfigboard.h" 2>/dev/null; then
    echo "  ⚠️  WARNING: PD9 referenced for UART - this is an FMC SDRAM pin!"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""
echo "=== Validation Summary ==="

if [ $ERRORS -gt 0 ]; then
    echo "❌ FAILED: $ERRORS error(s) found"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo "⚠️  PASSED with $WARNINGS warning(s)"
    exit 0
else
    echo "✅ PASSED: All checks passed"
    exit 0
fi
