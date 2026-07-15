#!/bin/bash
# SeedKeeper Smartcard Fix Test Matrix Builder
# Builds all 8 firmware variants with different combinations of fixes
#
# Usage: ./test_matrix.sh [clean]
#
# Three fixes being tested:
#   SCARD_FIX_HALFDUPLEX - Proper half-duplex UART handling (PR #40)
#   SCARD_FIX_T1_RECONFIG - T=1 protocol USART reconfiguration (PR #41)
#   SCARD_FIX_PPS        - Smart PPS negotiation (not yet in upstream)
#
# Test Matrix:
#   V0: no fixes (baseline - expected FAIL)
#   V1: PPS only
#   V2: T1_RECONFIG only
#   V3: HALFDUPLEX only
#   V4: T1_RECONFIG + PPS
#   V5: HALFDUPLEX + PPS
#   V6: HALFDUPLEX + T1_RECONFIG
#   V7: all fixes (expected PASS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$PROJECT_ROOT/bin/variants"
DOCKER_IMAGE="specter24d"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Build a single variant
# Args: variant_name, cflags
build_variant() {
    local name="$1"
    local cflags="$2"
    local output_file="$BIN_DIR/${name}.bin"
    
    log_info "Building $name with CFLAGS: $cflags"
    
    cd "$PROJECT_ROOT"
    
    # Build using Docker
    docker run --rm -v "$PROJECT_ROOT:/app" -w /app $DOCKER_IMAGE \
        bash -c "make disco USE_DBOOT=0 DEBUG=0 EXTRA_CFLAGS=\"$cflags\""
    
    if [ $? -eq 0 ] && [ -f "$PROJECT_ROOT/bin/specter-diy.bin" ]; then
        mkdir -p "$BIN_DIR"
        cp "$PROJECT_ROOT/bin/specter-diy.bin" "$output_file"
        log_info "✓ $name built successfully -> $output_file"
        return 0
    else
        log_error "✗ $name build failed"
        return 1
    fi
}

# Build all variants
build_all() {
    log_info "Starting test matrix build..."
    log_info "Project root: $PROJECT_ROOT"
    log_info "Output directory: $BIN_DIR"
    
    mkdir -p "$BIN_DIR"
    
    local failed=0
    local built=0
    
    # V0: Baseline (no fixes)
    if build_variant "V0_baseline" ""; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V1: PPS only
    if build_variant "V1_pps" "-DSCARD_FIX_PPS"; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V2: T1_RECONFIG only
    if build_variant "V2_t1reconfig" "-DSCARD_FIX_T1_RECONFIG"; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V3: HALFDUPLEX only
    if build_variant "V3_halfduplex" "-DSCARD_FIX_HALFDUPLEX"; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V4: T1_RECONFIG + PPS
    if build_variant "V4_t1_pps" "-DSCARD_FIX_T1_RECONFIG -DSCARD_FIX_PPS"; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V5: HALFDUPLEX + PPS
    if build_variant "V5_hd_pps" "-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_PPS"; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V6: HALFDUPLEX + T1_RECONFIG
    if build_variant "V6_hd_t1" "-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_T1_RECONFIG"; then
        ((built++))
    else
        ((failed++))
    fi
    
    # V7: All fixes
    if build_variant "V7_all" "-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_T1_RECONFIG -DSCARD_FIX_PPS"; then
        ((built++))
    else
        ((failed++))
    fi
    
    echo ""
    log_info "=========================================="
    log_info "Build Summary: $built succeeded, $failed failed"
    log_info "=========================================="
    
    if [ $failed -gt 0 ]; then
        return 1
    fi
    return 0
}

# Clean build artifacts
clean() {
    log_info "Cleaning build artifacts..."
    cd "$PROJECT_ROOT"
    docker run --rm -v "$PROJECT_ROOT:/app" -w /app $DOCKER_IMAGE make clean
    rm -rf "$BIN_DIR"
    log_info "Clean complete"
}

# Main
case "${1:-}" in
    clean)
        clean
        ;;
    *)
        if [ "${1:-}" != "" ]; then
            log_warn "Unknown argument: $1"
            echo "Usage: $0 [clean]"
            exit 1
        fi
        build_all
        ;;
esac
