#!/usr/bin/env bash

set -e
INFO="\e[1;36m"
ENDCOLOR="\e[0m"

SPECTER_DOCKER_IMAGE="${SPECTER_DOCKER_IMAGE:-specter24d}"
SPECTER_USE_DOCKER="${SPECTER_USE_DOCKER:-1}"

run_firmware_make() {
  local target="$1"
  shift || true
  if [ "$SPECTER_USE_DOCKER" = "1" ]; then
    sudo mkdir -p bin
    sudo chown -R "$(id -u):$(id -g)" bin f469-disco/micropython/mpy-cross f469-disco/micropython/ports/stm32/build-STM32F469DISC 2>/dev/null || true
    sudo docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/app" -w /app "$SPECTER_DOCKER_IMAGE" make "$target" "$@"
  else
    make "$target" "$@"
  fi
}

usage() {
  echo "Usage: $0 [all|release|main|bootloader|assemble|nobootloader|sign|hash|ownership|devboot-init|devboot-upgrade|devboot-check] ..."
  exit 1
}

# If no args, default to "all"
if [ $# -eq 0 ]; then
  ACTIONS=("all")
else
  ACTIONS=("$@")
fi

run_main() {
  echo -e "${INFO}
══════════════════════ Building main firmware ═════════════════════════════
${ENDCOLOR}"
  run_firmware_make clean
  run_firmware_make disco USE_DBOOT=1
}

run_bootloader() {
  echo -e "${INFO}
═════════════════════ Building secure bootloader ══════════════════════════
${ENDCOLOR}"
  cd bootloader
  make clean
  make stm32f469disco READ_PROTECTION=1 WRITE_PROTECTION=1
  cd -
}

run_assemble() {
  echo -e "${INFO}
══════════════════════ Assembling final binaries ══════════════════════════
${ENDCOLOR}"

  # --- Dependency checks ---
  REQUIRED_FILES=(
    "./bin/specter-diy.hex"
    "./bootloader/build/stm32f469disco/startup/release/startup.hex"
    "./bootloader/build/stm32f469disco/bootloader/release/bootloader.hex"
  )

  MISSING=0
  for f in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$f" ]; then
      echo -e "\e[1;31mERROR:\e[0m Required file missing: $f"
      MISSING=1
    fi
  done

  if [ "$MISSING" -eq 1 ]; then
    echo -e "\nOne or more required components were not built."
    echo -e "Please run: \e[1m./build_firmware.sh main bootloader\e[0m\n"
    exit 1
  fi
  # ---------------------------


  mkdir -p release

  python3 ./bootloader/tools/make-initial-firmware.py \
    -s ./bootloader/build/stm32f469disco/startup/release/startup.hex \
    -b ./bootloader/build/stm32f469disco/bootloader/release/bootloader.hex \
    -f ./bin/specter-diy.hex \
    -bin ./release/initial_firmware.bin
  echo -e "Initial firmware saved to release/initial_firmware.bin"

  python3 ./bootloader/tools/upgrade-generator.py gen \
    -f ./bin/specter-diy.hex \
    -b ./bootloader/build/stm32f469disco/bootloader/release/bootloader.hex \
    -p stm32f469disco \
    ./release/specter_upgrade.bin

  cp ./release/specter_upgrade.bin ./release/specter_upgrade_unsigned.bin
  echo "Unsigned upgrade file saved to release/specter_upgrade_unsigned.bin"

  HASH=$(python3 ./bootloader/tools/upgrade-generator.py message ./release/specter_upgrade.bin)
  echo "
╔════════════════════════════════════════════════════════════════════════════════╗
║                        Message to sign with vendor keys:                       ║
║                                                                                ║
║    ${HASH}    ║
║                                                                                ║
╚════════════════════════════════════════════════════════════════════════════════╝
"
}

run_nobootloader() {
  echo -e "${INFO}
═════════════════════ Building firmware without bootloader ════════════════
${ENDCOLOR}"

  mkdir -p release
  run_firmware_make clean
  run_firmware_make disco
  cp ./bin/specter-diy.bin ./release/disco-nobootloader.bin
  cp ./bin/specter-diy.hex ./release/disco-nobootloader.hex
  echo -e "Standard firmware without bootloader saved to release/disco-nobootloader.{bin,hex}"
  echo -e "The BIN image can be flashed directly to a development board without the secure bootloader."
}

run_sign() {
  echo -e "${INFO}
═════════════════════ Adding signature to the binary ══════════════════════
${ENDCOLOR}"

  # --- Dependency checks ---
  REQUIRED_FILES=(
    "./release/specter_upgrade.bin"
  )

  MISSING=0
  for f in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$f" ]; then
      echo -e "\e[1;31mERROR:\e[0m Required file missing: $f"
      MISSING=1
    fi
  done

  if [ "$MISSING" -eq 1 ]; then
    echo -e "\nOne or more required components were not built."
    echo -e "Please run: \e[1m./build_firmware.sh assemble\e[0m\n"
    exit 1
  fi
  # ---------------------------

  while true; do
    echo "Provide a signature to add to the upgrade file, or just hit enter to stop."
    read -r SIGNATURE
    if [ -z "$SIGNATURE" ]; then
      break
    fi
    python3 ./bootloader/tools/upgrade-generator.py import-sig -s "$SIGNATURE" ./release/specter_upgrade.bin
    echo "Signature added: ${SIGNATURE}"
  done
}

run_hash() {
  echo -e "${INFO}
═════════════════════════ Hashes of the binaries: ═════════════════════════
${ENDCOLOR}"

  mkdir -p release
  cd release
  sha256sum *.bin > sha256.txt
  cat sha256.txt
  echo "
Hashes saved to release/sha256.txt file.
"
  cd -
}

run_devboot_init() {
  echo -e "${INFO}
══════════════════════ Bootloader debug init bundle ════════════════════════
${ENDCOLOR}"

  mkdir -p release

  run_firmware_make clean
  run_firmware_make disco USE_DBOOT=1

  cd bootloader
  make clean
  make stm32f469disco KEYS=dev_unsigned ALLOW_UNSIGNED_UPGRADE=1 READ_PROTECTION=0 WRITE_PROTECTION=0
  cd -

  python3 ./bootloader/tools/make-initial-firmware.py \
    -s ./bootloader/build/stm32f469disco/startup/release/startup.hex \
    -b ./bootloader/build/stm32f469disco/bootloader/release/bootloader.hex \
    -f ./bin/specter-diy.hex \
    -bin ./release/initial_firmware_devboot_unsigned.bin

  python3 ./bootloader/tools/upgrade-generator.py gen \
    -f ./bin/specter-diy.hex \
    -p stm32f469disco \
    ./release/specter_upgrade_dev_unsigned.bin

  cp ./release/specter_upgrade_dev_unsigned.bin ./release/specter_upgrade.bin

  echo "Created:"
  echo "  release/initial_firmware_devboot_unsigned.bin"
  echo "  release/specter_upgrade_dev_unsigned.bin"
  echo "  release/specter_upgrade.bin"
}

run_devboot_upgrade() {
  echo -e "${INFO}
═══════════════════════ Bootloader debug fast upgrade ══════════════════════
${ENDCOLOR}"

  mkdir -p release

  run_firmware_make disco USE_DBOOT=1

  python3 ./bootloader/tools/upgrade-generator.py gen \
    -f ./bin/specter-diy.hex \
    -p stm32f469disco \
    ./release/specter_upgrade_dev_unsigned.bin

  cp ./release/specter_upgrade_dev_unsigned.bin ./release/specter_upgrade.bin

  echo "Created:"
  echo "  release/specter_upgrade_dev_unsigned.bin"
  echo "  release/specter_upgrade.bin"
}

run_devboot_check() {
  echo -e "${INFO}
══════════════════════ Verifying debug bootloader artifacts ═════════════════
${ENDCOLOR}"

  local required=(
    "./bin/specter-diy.hex"
    "./release/specter_upgrade_dev_unsigned.bin"
  )

  local missing=0
  local f=""
  for f in "${required[@]}"; do
    if [ ! -f "$f" ]; then
      echo -e "\e[1;31mERROR:\e[0m Required file missing: $f"
      missing=1
    fi
  done

  if [ "$missing" -eq 1 ]; then
    echo -e "\nBuild missing artifacts first with: \e[1m./build_firmware.sh devboot-upgrade\e[0m\n"
    exit 1
  fi

  python3 - <<'PY'
import re
import subprocess
import sys
from intelhex import IntelHex

hex_path = "bin/specter-diy.hex"
upgrade_path = "release/specter_upgrade_dev_unsigned.bin"
expected = 0x08020000

base_addr = IntelHex(hex_path).minaddr()
if base_addr != expected:
    print(f"ERROR: {hex_path} base address is 0x{base_addr:08x}, expected 0x{expected:08x} (USE_DBOOT=1 build)")
    sys.exit(1)

dump = subprocess.check_output(
    ["python3", "./bootloader/tools/upgrade-generator.py", "dump", upgrade_path],
    text=True,
)

if 'SECTION "main"' not in dump:
    print("ERROR: upgrade file does not contain main firmware payload section")
    sys.exit(1)

if "stm32f469disco" not in dump:
    print("ERROR: upgrade file platform attribute is missing stm32f469disco")
    sys.exit(1)

if not re.search(r"0x0*8020000|0x0*08020000", dump, flags=re.IGNORECASE):
    print("ERROR: upgrade payload base address does not look DBOOT-compatible (0x08020000)")
    print(dump)
    sys.exit(1)

print("OK: firmware hex base address is 0x08020000")
print("OK: upgrade contains SECTION \"main\" for stm32f469disco")
print("OK: upgrade dump reports DBOOT-compatible base address")
PY

  echo ""
  echo "Hardware test quick steps:"
  echo "  1) One-time: flash release/initial_firmware_devboot_unsigned.bin to the board."
  echo "  2) For each cycle: copy release/specter_upgrade_dev_unsigned.bin to SD as specter_upgrade.bin."
  echo "  3) Reboot device and observe Satochip secure channel logs (USB VCP or ST-Link UART)."
}

fix_ownership() {
  echo -e "${INFO}
═════════════════════════ Fixing file ownership ═══════════════════════════
${ENDCOLOR}"

  if [ -n "$HOST_UID" ] && [ -n "$HOST_GID" ]; then
    chown -R "$HOST_UID:$HOST_GID" bin 2>/dev/null || true
    chown -R "$HOST_UID:$HOST_GID" release 2>/dev/null || true
    chown -R "$HOST_UID:$HOST_GID" f469-disco/micropython/mpy-cross 2>/dev/null || true
    chown -R "$HOST_UID:$HOST_GID" bootloader 2>/dev/null || true
    echo "File ownership changed to local user/group"
  else
    echo "Skipping fix_ownership: HOST_UID and HOST_GID not set."
  fi
}

# Map action_name to function
dispatch() {
  case "$1" in
    all)
      run_main
      run_bootloader
      run_assemble
      run_sign
      run_nobootloader
      run_hash
      fix_ownership
      ;;
    release)
      run_main
      run_bootloader
      run_assemble
      run_sign
      run_hash
      fix_ownership
      ;;
    main)          run_main ;;
    bootloader)    run_bootloader ;;
    assemble)      run_assemble ;;
    nobootloader)  run_nobootloader ;;
    sign)          run_sign ;;
    hash)          run_hash ;;
    ownership)     fix_ownership ;;
    devboot-init)  run_devboot_init ;;
    devboot-upgrade) run_devboot_upgrade ;;
    devboot-check) run_devboot_check ;;
    *) echo "Unknown action: $1"; usage ;;
  esac
}

# Execute requested actions in order
for action in "${ACTIONS[@]}"; do
  dispatch "$action"
done
