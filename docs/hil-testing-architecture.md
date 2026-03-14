# Hardware-in-Loop Testing Architecture

## Overview
This document defines a hardware-in-loop (HIL) testing architecture for Specter-DIY on STM32F469 Discovery hardware. The goal is to run the same high-level integration intent currently exercised in simulator tests against real hardware, with deterministic control of lifecycle (flash/reset/boot) and deterministic control of user interactions (PIN entry, confirm/cancel, signing prompts).

The current integration contract is visible in `test/integration/util/controller.py` via `SimController.query(self, data, commands=[])`. Existing tests in `test/integration/tests/test_basic.py` and `test/integration/tests/test_with_rpc.py` send host protocol payloads (for example `sign`, `xpub`, `showaddr`, `addwallet`) and inject UI actions through the `commands` array. The HIL design keeps this test-side contract stable and swaps only the transport/controller implementation.

## Hardware Setup

### ST-Link Connection
- Use ST-Link V2 SWD for firmware lifecycle operations (flash and hard reset).
- Use UART3 on PB10/PB11 as the control channel over virtual COM when wired to ST-Link.
- On Linux, expect `/dev/ttyACM0` style devices (see `udev/49-micropython.rules`).
- On macOS, expect `/dev/tty.usbmodem*` style devices (also reflected in `docs/development.md`).

Board-level UART3 pin assumptions are consistent with:
- `f469-disco/micropython/ports/stm32/boards/STM32F469DISC/mpconfigboard.h`
- `f469-disco/micropython/ports/stm32/boards/STM32F469DISC/pins.csv`
- `scripts/validate_pins.sh`

### Test Environment Requirements
- `st-flash` installed and accessible in `PATH`.
- Python `pyserial` package available for UART communication.
- Physical ST-Link attachment to the target board for SWD lifecycle control.
- A known serial device mapping for the board before test start.

## Control Channel Protocol

### UART3 VCP Configuration
- Baud rate: `115200`
- Data bits: `8`
- Parity: `None`
- Stop bits: `1`
- Flow control: `None`

Important distinction:
- `src/platform.py:316` configures `pyb.UART("YB", 9600)` for debug/dupterm usage.
- HIL control channel should use UART3 VCP at `115200` and remain independent from the debug UART path.

### Command Protocol
For HIL, map simulator semantics to a UART test-agent protocol while preserving the `query(data, commands=[])` contract from `test/integration/util/controller.py`.

| SimController semantic | TestMode UART command | Description |
|---|---|---|
| USB data payload | `TEST_SIGN:<hex>` | Submit signing payload (for example PSBT bytes in hex). |
| GUI confirm | `TEST_UI_SET:confirm` | Confirm current modal/prompt. |
| GUI cancel | `TEST_UI_SET:cancel` | Reject current modal/prompt. |
| PIN entry | `TEST_UI_PIN:<digits>` | Inject PIN digits into active PIN flow. |

Additional control commands expected by runner:
- `TEST_STATUS` -> liveness/ready probe, expected response prefix `OK:`.
- `TEST_RESET` -> soft reset between test cases without SWD cycle.

Example UART line protocol (ASCII, newline-terminated):

```text
TEST_STATUS
OK:READY
TEST_UI_SET:confirm
OK:UI
TEST_SIGN:7369676e2063656e7472616c5f7061796c6f6164
OK:RESULT:...
```

## Lifecycle Operations

### Firmware Flashing
Use SWD for deterministic startup state:

```bash
st-flash --reset write specter-diy.bin 0x08000000
```

This is consistent with project guidance in `docs/quickstart.md` and bootloader docs under `bootloader/doc/`.

### Device Reset

```bash
st-flash reset
```

Reset hierarchy:
1. Soft reset: `TEST_RESET` over UART (fast path between tests).
2. Hard reset: `st-flash reset` over SWD (recover from UART lockups).
3. Reflash + reset: last-resort recovery for unrecoverable test state.

### Boot Detection
- Open UART3 VCP and poll for responsiveness.
- Send `TEST_STATUS`; require response starting with `OK:`.
- Boot timeout: `10` seconds.
- If timeout occurs, escalate from soft reset to hard reset.

## Test Runner Architecture

### HardwareController Interface
The hardware controller mirrors simulator shape to minimize test churn:

```python
class HardwareController:
    def start(self): ...      # establish serial + optional SWD helpers
    def load(self): ...       # initialize wallet test state
    def shutdown(self): ...   # close transport/process handles
    def query(self, data, commands=[]): ...  # same contract as SimController
```

Recommended transport split:
- `UARTChannel`: open/close/readline/write with strict timeouts.
- `HardwareController`: translate simulator-style actions into UART test-agent commands and host payload forwarding.

### Test Execution Flow
1. Flash firmware if binary hash changed or run requests clean image.
2. Hard reset device.
3. Wait for boot (`TEST_STATUS` probe).
4. Execute each test action through `query()`.
5. Soft reset between tests with `TEST_RESET`.
6. Collect UART transcript and test assertions.

Minimal host-side pseudocode:

```python
def query(self, data, commands=[]):
    self.channel.send_payload(data)
    for command in commands:
        if command is True:
            self.channel.send_line("TEST_UI_SET:confirm")
        elif command is False:
            self.channel.send_line("TEST_UI_SET:cancel")
        elif isinstance(command, str) and command.isdigit():
            self.channel.send_line(f"TEST_UI_PIN:{command}")
    return self.channel.read_result(timeout=5.0)
```

## Test Cases

### Keystore Tests
- PIN entry and verification flows.
- Secret storage/retrieval coverage.
- SeedKeeper-related storage operations where enabled.

Reference command-heavy test patterns in `test/integration/tests/test_basic.py`.

### Signing Tests
- Transaction signing over PSBT payloads.
- Message signing flows.
- Multi-script and sighash behavior parity with simulator scenarios.

Reference wide signing matrix in `test/integration/tests/test_with_rpc.py`.

### Display Tests
- Prompt/confirm/cancel screen state transitions.
- Address display verification (`showaddr` style flows).
- Optional QR rendering checks where camera/decoder fixture exists.

## Error Handling

### Timeout Handling
- UART read timeout: `5` seconds.
- Boot timeout: `10` seconds.
- Per-test timeout: `60` seconds.

Runner should classify timeout source explicitly (boot, command ack, result payload) to improve triage.

### Recovery
- First retry: `TEST_RESET`.
- Second retry: `st-flash reset`.
- Final retry: reflash firmware and restart test item.

Persist failure artifacts:
- Last N UART lines.
- Last command sent.
- Current test id and step index.

## Implementation Checklist
- [ ] `UARTChannel` class (`pyserial` wrapper, strict read/write timeouts).
- [ ] `HardwareController` class implementing simulator-compatible `query` contract.
- [ ] Runner wiring to select simulator vs hardware backend.
- [ ] Device lifecycle helper for flash/reset/boot probe.
- [ ] Failure artifact capture for deterministic debugging.

## References
- `src/platform.py` - debug UART setup (`pyb.UART("YB", 9600)`) and USB mode controls.
- `test/integration/util/controller.py` - `SimController` and `query(data, commands=[])` interface.
- `test/integration/tests/test_basic.py` - baseline integration test semantics.
- `test/integration/tests/test_with_rpc.py` - signing and RPC-backed integration coverage.
- `f469-disco/micropython/ports/stm32/boards/STM32F469DISC/mpconfigboard.h` - board UART definitions.
- `f469-disco/micropython/ports/stm32/boards/STM32F469DISC/pins.csv` - UART3 pin mapping for PB10/PB11.
- `scripts/validate_pins.sh` - pin validation checks for UART3 TX/RX.
- `docs/development.md` - serial console examples at `115200` baud.
- `docs/quickstart.md` - `st-flash` usage guidance.
