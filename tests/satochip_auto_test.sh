#!/bin/bash
# Satochip Automated Test Runner
# Uses TEST_* commands for fully automated testing without manual input
#
# Usage: ./satochip_auto_test.sh [--build] [--flash] [--pin=1234] [--network=main|test|signet|regtest]
#
# Prerequisites:
# - Satochip card inserted in device
# - Device connected via USB (serial + debug)
# - probe-rs installed on remote host

set -e

# Config
REMOTE=ubuntu@192.168.13.246
SERIAL_DEV=/dev/ttyACM0
DEFAULT_PIN=1234
TIMEOUT_CMD=60
NETWORK=main
ACCOUNT0=0
ACCOUNT1=1

# Parse args
BUILD=0
FLASH=0
PIN=$DEFAULT_PIN

for arg in "$@"; do
    case $arg in
        --build) BUILD=1 ;;
        --flash) FLASH=1 ;;
        --pin=*) PIN="${arg#*=}" ;;
        --network=*) NETWORK="${arg#*=}" ;;
        --account0=*) ACCOUNT0="${arg#*=}" ;;
        --account1=*) ACCOUNT1="${arg#*=}" ;;
        --serial-dev=*) SERIAL_DEV="${arg#*=}" ;;
    esac
done

if [ "$NETWORK" = "main" ]; then
    COIN=0
    ADDR_PREFIX=bc1
else
    COIN=1
    ADDR_PREFIX=tb1
fi

ACCOUNT_PATH0="m/84h/${COIN}h/${ACCOUNT0}h"
ACCOUNT_PATH1="m/84h/${COIN}h/${ACCOUNT1}h"
SIGN_PATH0="${ACCOUNT_PATH0}/0/0"
SIGN_PATH1="${ACCOUNT_PATH1}/1/3"

# Test counters
PASS=0; FAIL=0; TOTAL=0
LOG_FILE="satochip_auto_test_log.txt"

echo "============================================================"
echo "Satochip Automated Test Runner"
echo "============================================================"
echo "PIN: $PIN"
echo "Build: $BUILD"
echo "Flash: $FLASH"
echo "Serial: $SERIAL_DEV"
echo "Network: $NETWORK"
echo "Account #0 path: $ACCOUNT_PATH0"
echo "Account #1 path: $ACCOUNT_PATH1"
echo ""

# Functions
build() {
    echo "[BUILD] Building Satochip firmware..."
    ssh $REMOTE "sudo docker run --rm -v /home/ubuntu/specter-diy:/app -w /app specter24d bash -c 'make disco USE_DBOOT=0'"
    if [ $? -ne 0 ]; then
        echo "❌ Build failed!"
        exit 1
    fi
    echo "✓ Build successful"
}

flash() {
    echo "[FLASH] Flashing firmware..."
    ssh $REMOTE "/home/ubuntu/.local/bin/probe-rs download --protocol swd --chip STM32F469NI ~/specter-diy/f469-disco/micropython/ports/stm32/build-STM32F469DISC/firmware.elf"
    if [ $? -ne 0 ]; then
        echo "❌ Flash failed!"
        exit 1
    fi
    echo "✓ Flash successful"
    
    echo "[FLASH] Resetting device..."
    ssh $REMOTE "/home/ubuntu/.local/bin/probe-rs reset --protocol swd --chip STM32F469NI"
    sleep 3
}

send_cmd() {
    local cmd=$1
    local timeout=${2:-10}
    echo "[CMD] $cmd"
    
    # Send command and capture response
    # Using expect-like approach with timeout
    result=$(ssh $REMOTE "echo '$cmd' > $SERIAL_DEV && timeout $timeout cat $SERIAL_DEV 2>/dev/null | head -20" 2>/dev/null || true)
    echo "$result"
    echo "$result"
}

send_cmd_expect() {
    local cmd=$1
    local expect_pattern=$2
    local timeout=${3:-10}
    
    echo "[TEST] Sending: $cmd"
    echo "[TEST] Expecting: $expect_pattern"
    
    # Send command and wait for response
    response=$(ssh $REMOTE "
        stty -F $SERIAL_DEV 115200 raw -echo 2>/dev/null || true
        echo '$cmd' > $SERIAL_DEV
        timeout $timeout cat $SERIAL_DEV 2>/dev/null | grep -m1 -E 'RESP: (OK|ERROR):' || echo 'TIMEOUT'
    " 2>/dev/null || echo "TIMEOUT")
    
    echo "[RESP] $response"
    
    if echo "$response" | grep -q "$expect_pattern"; then
        echo "✓ PASS: $cmd -> $expect_pattern"
        PASS=$((PASS + 1))
    else
        echo "❌ FAIL: $cmd -> expected '$expect_pattern', got '$response'"
        FAIL=$((FAIL + 1))
    fi
    TOTAL=$((TOTAL + 1))
    if echo "$response" | grep -q "$expect_pattern"; then
        return 0
    fi
    return 1
}

send_cmd_capture() {
    local cmd=$1
    local timeout=${2:-10}
    response=$(ssh $REMOTE "
        stty -F $SERIAL_DEV 115200 raw -echo 2>/dev/null || true
        echo '$cmd' > $SERIAL_DEV
        timeout $timeout cat $SERIAL_DEV 2>/dev/null | grep -m1 -E 'RESP: (OK|ERROR):' || echo 'TIMEOUT'
    " 2>/dev/null || echo "TIMEOUT")
    echo "$response"
}

run_serial_test() {
    echo ""
    echo "============================================================"
    echo "Running Automated Serial Tests"
    echo "============================================================"
    
    # Wait for boot
    echo "[BOOT] Waiting for device to boot..."
    sleep 5
    
    # Test 1: Check boot state before unlock
    send_cmd_expect "TEST_BOOT_STATE" "is_ready.*False" 10 || true
    
    # Test 2: Unlock with PIN
    send_cmd_expect "TEST_PIN:$PIN" "OK:PIN verified" 15
    
    # Test 3: Wait for keystore ready
    send_cmd_expect "TEST_WAIT_READY" "OK:ready" 35

    send_cmd_expect "TEST_SET_NETWORK:$NETWORK" "OK:network_set:$NETWORK" 10
    
    # Test 4: Verify boot state after unlock
    send_cmd_expect "TEST_BOOT_STATE" "is_ready.*True" 10
    
    # Test 5: AEAD smoke test
    send_cmd_expect "TEST_WALLET_SMOKE" "OK:wallet_smoke_passed" 10
    
    send_cmd_expect "TEST_XPUB:$ACCOUNT_PATH0" "OK:" 15
    send_cmd_expect "TEST_XPUB:$ACCOUNT_PATH1" "OK:" 15
    
    HASH0=0000000000000000000000000000000000000000000000000000000000000000
    HASH1=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
    send_cmd_expect "TEST_SIGN_AT:$SIGN_PATH0:$HASH0" "OK:" 20
    send_cmd_expect "TEST_SIGN_AT:$SIGN_PATH1:$HASH1" "OK:" 20

    SIG_A=$(send_cmd_capture "TEST_SIGN_AT:$SIGN_PATH0:$HASH0" 20)
    SIG_B=$(send_cmd_capture "TEST_SIGN_AT:$SIGN_PATH0:$HASH0" 20)
    if echo "$SIG_A" | grep -q "RESP: OK:" && echo "$SIG_B" | grep -q "RESP: OK:"; then
        PASS=$((PASS + 1))
        echo "✓ PASS: repeated signing returned valid signatures"
        if [ "$SIG_A" = "$SIG_B" ]; then
            echo "[INFO] Repeated signatures matched exactly"
        else
            echo "[INFO] Repeated signatures differed (acceptable on JavaCard ECDSA)"
        fi
    else
        FAIL=$((FAIL + 1))
        echo "❌ FAIL: repeated signing did not return two OK responses"
        echo "  SIG_A=$SIG_A"
        echo "  SIG_B=$SIG_B"
    fi
    TOTAL=$((TOTAL + 1))
    
    send_cmd_expect "TEST_GET_ADDRESS:${ACCOUNT_PATH0}/0/0" "OK:${ADDR_PREFIX}" 15
    send_cmd_expect "TEST_GET_ADDRESS:${ACCOUNT_PATH1}/0/0" "OK:${ADDR_PREFIX}" 15
    
    # Test 9: Full comprehensive check
    send_cmd_expect "TEST_FULL_CHECK" "FULL_CHECK_PASSED" 30
    
    # Test 10: Screen info
    send_cmd_expect "TEST_SCREEN" "OK:" 5
}

# Main
if [ $BUILD -eq 1 ]; then
    build
fi

if [ $FLASH -eq 1 ]; then
    flash
fi

# Run tests
run_serial_test

# Report
echo ""
echo "============================================================"
echo "FINAL TEST REPORT"
echo "============================================================"
echo "Total Passed: $PASS"
echo "Total Failed: $FAIL"
echo "Total Tests:  $TOTAL"
echo "============================================================"

if [ $FAIL -eq 0 ]; then
    echo "✓ ALL TESTS PASSED!"
    exit 0
else
    echo "❌ SOME TESTS FAILED!"
    exit 1
fi
