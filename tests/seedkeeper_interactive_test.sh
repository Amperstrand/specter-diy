#!/bin/bash
# Comprehensive SeedKeeper Interactive Test Protocol
# Uses 'say' for audio prompts and captures serial output

REMOTE=ubuntu@192.168.13.246
SERIAL_DEV=/dev/ttyACM1
EVIDENCE_DIR="/Users/macbook/src/seedkeeperport/.sisyphus/evidence"
LOG_FILE="$EVIDENCE_DIR/comprehensive-test-$(date +%Y%m%d-%H%M%S).txt"

# Colors for terminal
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass=0
fail=0

say_and_print() {
    echo "$1"
    say "$1"
}

reset_and_capture() {
    local duration=${1:-120}
    echo "Resetting board and capturing serial for ${duration}s..."
    ssh $REMOTE "st-flash reset 2>&1; sleep 2; timeout $duration cat $SERIAL_DEV 2>/dev/null" > $LOG_FILE 2>&1 &
    CAPTURE_PID=$!
    sleep 3  # Wait for boot to begin
}

stop_capture() {
    if [ ! -z "$CAPTURE_PID" ]; then
        kill $CAPTURE_PID 2>/dev/null || true
    fi
}

wait_for_capture() {
    if [ ! -z "$CAPTURE_PID" ]; then
        wait $CAPTURE_PID 2>/dev/null || true
    fi
}

assert_pattern() {
    local pattern="$1"
    local test_name="$2"
    if grep -q "$pattern" $LOG_FILE; then
        echo -e "${GREEN}[PASS]${NC} $test_name: Found '$pattern'"
        pass=$((pass + 1))
        return 0
    else
        echo -e "${RED}[FAIL]${NC} $test_name: Missing '$pattern'"
        fail=$((fail + 1))
        return 1
    fi
}

reject_pattern() {
    local pattern="$1"
    local test_name="$2"
    if grep -q "$pattern" $LOG_FILE; then
        echo -e "${RED}[FAIL]${NC} $test_name: Unexpected '$pattern' found"
        fail=$((fail + 1))
        return 1
    else
        echo -e "${GREEN}[PASS]${NC} $test_name: '$pattern' not found (as expected)"
        pass=$((pass + 1))
        return 0
    fi
}

visual_check() {
    local prompt="$1"
    local test_name="$2"
    echo -e "${YELLOW}[VISUAL]${NC} $test_name: $prompt"
    say "$prompt. Please respond yes or no."
    read -p "Did you see this? (y/n): " response
    if [[ "$response" =~ ^[Yy] ]]; then
        echo -e "${GREEN}[PASS]${NC} $test_name: Visual check confirmed"
        pass=$((pass + 1))
        return 0
    else
        echo -e "${RED}[FAIL]${NC} $test_name: Visual check failed"
        fail=$((fail + 1))
        return 1
    fi
}

print_serial_snippet() {
    echo "--- Serial Output Snippet ---"
    tail -20 $LOG_FILE
    echo "------------------------------"
}

# Start test
echo "========================================"
echo "SeedKeeper Comprehensive Interactive Test"
echo "========================================"
echo "Evidence file: $LOG_FILE"
echo ""

# TC-01: Correct PIN Flow
say_and_print "Test Case 1: Correct PIN flow. I will reset the board. When the PIN screen appears, enter PIN one two three four."
reset_and_capture 90

# Wait for user to enter PIN
sleep 15
say "Please enter PIN one two three four now."

# Wait for boot to complete
sleep 30

print_serial_snippet

# TC-01 Assertions
echo ""
echo "=== TC-01: Correct PIN Flow ==="
assert_pattern "is_available = True" "TC-01: SeedKeeper detected"
assert_pattern "Selected keystore: SeedKeeper" "TC-01: Correct keystore selected"
assert_pattern "PIN attempts remaining:" "TC-01: PIN attempts displayed"
assert_pattern "PIN verified successfully" "TC-01: PIN verified"
assert_pattern "Mnemonic loaded successfully" "TC-01: Mnemonic loaded"

wait_for_capture

# TC-02: Wrong PIN then Correct
say_and_print "Test Case 2: Wrong PIN then correct. I will reset the board. When the PIN screen appears, enter wrong PIN nine nine nine nine, then after the error, enter correct PIN one two three four."
reset_and_capture 120

sleep 15
say "Please enter wrong PIN nine nine nine nine now."

sleep 20
say "Press OK on the error alert, then enter correct PIN one two three four."

sleep 40

print_serial_snippet

# TC-02 Assertions
echo ""
echo "=== TC-02: Wrong PIN then Correct ==="
assert_pattern "PIN attempts remaining:" "TC-02: Initial attempts shown"
reject_pattern "9c30" "TC-02: No 9c30 error (secure channel intact)"
assert_pattern "PIN verified successfully" "TC-02: Eventually verified"

wait_for_capture

# Summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Passed: ${GREEN}$pass${NC}"
echo -e "Failed: ${RED}$fail${NC}"
echo "Evidence: $LOG_FILE"
echo ""

if [ $fail -eq 0 ]; then
    say "All tests passed. Congratulations!"
    exit 0
else
    say "Some tests failed. Please check the evidence file."
    exit 1
fi
