#!/bin/bash
# Unified Smart Card Test Runner (Shell Wrapper)
# Detects card type automatically and runs appropriate tests
#
# Usage: ./unified_card_test.sh [--build] [--flash] [--reset]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE="${REMOTE:-ubuntu@192.168.13.246}"
SERIAL_DEV="${SERIAL_DEV:-/dev/ttyACM1}"
DURATION="${DURATION:-60}"
FIRMWARE_PATH="${FIRMWARE_PATH:-/home/ubuntu/seedkeeperonly/bin/specter-diy.bin}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Parse arguments
BUILD=false
FLASH=false
RESET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD=true
            shift
            ;;
        --flash)
            FLASH=true
            shift
            ;;
        --reset)
            RESET=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_header "Unified Smart Card Test Runner"

# Build if requested
if [ "$BUILD" = true ]; then
    print_info "Building firmware..."
    ssh "$REMOTE" 'cd /home/ubuntu/seedkeeperonly && sudo docker run --rm -v $(pwd):/app -w /app specter24d bash -lc "make clean && make disco USE_DBOOT=0 DEBUG=0"'
    if [ $? -eq 0 ]; then
        print_success "Build complete"
    else
        print_error "Build failed"
        exit 1
    fi
fi

# Flash if requested
if [ "$FLASH" = true ]; then
    print_info "Flashing firmware..."
    ssh "$REMOTE" "st-flash --connect-under-reset --reset write $FIRMWARE_PATH 0x08000000"
    if [ $? -eq 0 ]; then
        print_success "Flash complete"
        sleep 2  # Wait for device to boot
    else
        print_error "Flash failed"
        exit 1
    fi
fi

# Reset if requested
if [ "$RESET" = true ]; then
    print_info "Resetting board..."
    ssh "$REMOTE" "st-flash reset"
    sleep 2
fi

# Run the Python test runner
print_header "Running Tests"

python3 "$SCRIPT_DIR/unified_card_test.py" \
    --serial "$SERIAL_DEV" \
    --duration "$DURATION" \
    --remote "$REMOTE"

EXIT_CODE=$?

print_header "Test Complete"

if [ $EXIT_CODE -eq 0 ]; then
    print_success "All tests passed!"
else
    print_error "Some tests failed"
fi

exit $EXIT_CODE
