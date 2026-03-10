#!/bin/bash
# SeedKeeper Hybrid Test Runner
# Usage: ./seedkeeper_test.sh [--build] [--flash]

REMOTE=ubuntu@192.168.13.246
SERIAL_DEV=/dev/ttyACM1
PASS=0; FAIL=0; TOTAL=0
LOG_FILE="last_test_log.txt"

# Functions
build() {
    echo "Building SeedKeeper firmware..."
    ssh $REMOTE 'sudo docker run --rm -v /home/ubuntu/src/seedkeeperport/specter-diy-latest:/app -w /app specter24d bash -lc "export PATH=/opt/gcc-arm-none-eabi-9-2020-q2-update/bin:\$PATH && make disco USE_DBOOT=0 DEBUG=0"'
    if [ $? -ne 0 ]; then
        echo "❌ Build failed!"
        exit 1
    fi
    echo "✓ Build successful"
}

flash() {
    echo "Flashing firmware..."
    ssh $REMOTE 'st-flash --connect-under-reset --reset write /home/ubuntu/src/seedkeeperport/specter-diy-latest/bin/specter-diy.bin 0x08000000'
    if [ $? -ne 0 ]; then
        echo "❌ Flash failed!"
        exit 1
    fi
    echo "✓ Flash successful"
}

reset_and_capture() {
    local duration=${1:-90}
    echo "Resetting board and capturing serial output for ${duration}s..."
    ssh $REMOTE "st-flash reset 2>&1; sleep 2; timeout $duration cat /dev/ttyACM1 2>/dev/null" > $LOG_FILE
    if [ $? -ne 0 ]; then
        echo "❌ Serial capture failed!"
        exit 1
    fi
    echo "✓ Capture saved to $LOG_FILE"
}

stop_capture() {
    # No-op for this implementation - serial capture uses timeout
    true
}

assert_pattern() {
    local pattern=$1
    local test_name=$2
    if grep -q "$pattern" $LOG_FILE; then
        echo "✓ PASS: $test_name - pattern found: $pattern"
        PASS=$((PASS + 1))
    else
        echo "❌ FAIL: $test_name - pattern NOT found: $pattern"
        FAIL=$((FAIL + 1))
    fi
    TOTAL=$((TOTAL + 1))
}

reject_pattern() {
    local pattern=$1
    local test_name=$2
    if grep -q "$pattern" $LOG_FILE; then
        echo "❌ FAIL: $test_name - pattern found (should NOT be present): $pattern"
        FAIL=$((FAIL + 1))
    else
        echo "✓ PASS: $test_name - pattern NOT found as expected"
        PASS=$((PASS + 1))
    fi
    TOTAL=$((TOTAL + 1))
}

prompt_user() {
    echo ""
    echo "============================================================"
    echo "$1"
    echo "Press ENTER to continue..."
    read
}

report() {
    local test_name=$1
    local status="PASS"
    if [ $(echo "$test_name" | grep -c "FAIL") -gt 0 ]; then
        status="FAIL"
    fi
    echo "============================================================"
    echo "Test Case: $test_name"
    echo "Status: $status"
    echo "Total Passed: $PASS | Total Failed: $FAIL | Total: $TOTAL"
    echo "============================================================"
    echo ""
}

# Main script
if [ "$1" = "--build" ]; then
    build
fi

if [ "$1" = "--flash" ]; then
    flash
fi

reset_and_capture 90

# TC-01: Correct PIN flow
prompt_user "TC-01: Insert card and enter correct PIN (1234)"
prompt_user "Press ENTER when you've entered the PIN and see main menu"
stop_capture
assert_pattern "PIN verified successfully" "TC-01"
assert_pattern "[BootTrace][SeedKeeper] is_available = True" "TC-01"
assert_pattern "[BootTrace] Selected keystore: SeedKeeper" "TC-01"
assert_pattern "[BootTrace][SeedKeeper] PIN attempts remaining:" "TC-01"
assert_pattern "[BootTrace][SeedKeeper] Mnemonic loaded successfully" "TC-01"
assert_pattern "[BootTrace] keystore.unlock() done" "TC-01"
reject_pattern "unlock\(\).*unlock\(\)" "TC-01"
report "TC-01"

# TC-02: Wrong PIN then correct
reset_and_capture 90
prompt_user "TC-02: Enter WRONG PIN (0000), then correct PIN (1234)"
prompt_user "Press ENTER after entering the correct PIN"
assert_pattern "Wrong PIN" "TC-02"
assert_pattern "PIN verified successfully" "TC-02"
assert_pattern "[BootTrace][SeedKeeper] PIN attempts remaining:" "TC-02"
report "TC-02"

# TC-03: Wrong PIN twice then correct
reset_and_capture 90
prompt_user "TC-03: Enter WRONG PIN (0000), WRONG PIN again (1111), then correct PIN (1234)"
prompt_user "Press ENTER after entering the correct PIN"
assert_pattern "Wrong PIN" "TC-02"  # Reuse message
assert_pattern "PIN verified successfully" "TC-03"
assert_pattern "[BootTrace][SeedKeeper] PIN attempts remaining:" "TC-03"
report "TC-03"

# TC-04: Card identity subtitle visible
reset_and_capture 90
prompt_user "TC-04: Insert card - verify card identity subtitle is visible"
prompt_user "Press ENTER when you've seen the subtitle"
assert_pattern "Card Identity:" "TC-04"
assert_pattern "Subtitle:" "TC-04"
report "TC-04"

# TC-05: PIN attempts visible on first screen
reset_and_capture 90
prompt_user "TC-05: Insert card - verify PIN attempts count is visible on first screen"
prompt_user "Press ENTER when you've seen the PIN attempts count"
assert_pattern "PIN attempts remaining:" "TC-05"
assert_pattern "[BootTrace][SeedKeeper] PIN attempts remaining:" "TC-05"
report "TC-05"

# TC-06: PIN attempts decrease after wrong PIN
reset_and_capture 90
prompt_user "TC-06: Enter WRONG PIN (0000) and verify PIN attempts decrease"
prompt_user "Press ENTER after entering the wrong PIN"
assert_pattern "PIN attempts remaining:" "TC-06"
assert_pattern "[BootTrace][SeedKeeper] PIN attempts remaining:" "TC-06"
assert_pattern "Wrong PIN" "TC-06"
report "TC-06"

# Final report
echo "============================================================"
echo "FINAL TEST REPORT"
echo "============================================================"
echo "Total Passed: $PASS"
echo "Total Failed: $FAIL"
echo "Total Test Cases: $TOTAL"
echo "============================================================"

if [ $FAIL -eq 0 ]; then
    echo "✓ ALL TESTS PASSED!"
    exit 0
else
    echo "❌ SOME TESTS FAILED!"
    exit 1
fi
