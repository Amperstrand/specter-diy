# Hardware-in-the-Loop (HIL) Testing Architecture

This document defines the architecture for extending Specter-DIY's testing capabilities from simulator-only to real hardware testing with smart card peripherals.

---

## 1. Transport Analysis

### Current Simulator Transport Stack

The existing integration tests use a TCP socket abstraction that simulates USB communication:

| Component | File | Line | Class/Method | Transport-Specific? |
|-----------|------|------|--------------|---------------------|
| TCP Socket Client | `test/integration/util/controller.py` | 9-40 | `TCPSocket` | **Yes** - Unix simulator only |
| Socket Connection | `test/integration/util/controller.py` | 11-12 | `TCPSocket.__init__()` | **Yes** - TCP to 127.0.0.1 |
| Line Reading | `test/integration/util/controller.py` | 14-27 | `TCPSocket.readline()` | **Yes** - socket.recv() |
| Query Protocol | `test/integration/util/controller.py` | 34-36 | `TCPSocket.query()` | **Yes** - expects `b"ACK\r\n"` |
| Process Management | `test/integration/util/controller.py` | 51-56 | `SimController.start()` | **Yes** - subprocess.Popen |
| GUI Socket | `test/integration/util/controller.py` | 60 | `self.gui = TCPSocket(8787)` | **Yes** - port 8787 |
| USB Socket | `test/integration/util/controller.py` | 70 | `self.usb = TCPSocket(8789)` | **Yes** - port 8789 |

### Reusable Components (Transport-Agnostic)

| Component | File | Line | Class/Method | Reusable For Hardware? |
|-----------|------|------|--------------|------------------------|
| Query Pattern | `test/integration/util/controller.py` | 83-95 | `SimController.query()` | **Yes** - pattern reusable |
| ACK Protocol | `test/integration/util/controller.py` | 89 | `assert res == b"ACK\r\n"` | **Yes** - same protocol |
| Command Formatting | `test/integration/util/controller.py` | 84-87 | data encoding + CRLF | **Yes** - identical format |
| Response Handling | `test/integration/util/controller.py` | 94-95 | `receive()` + strip | **Yes** - same parsing |
| Test Logic | `test/integration/tests/test_basic.py` | 7-50 | `BasicTest` class | **Yes** - assertions unchanged |

### Key Insight

The `query(data, commands=[])` method at `controller.py:83-95` defines the **protocol contract**:
1. Send data with `\r\n` terminator
2. Wait for `ACK\r\n` acknowledgment
3. Optionally send GUI commands via separate channel
4. Receive response and strip whitespace

This contract is transport-agnostic and can be implemented over UART3 VCP.

---

## 2. HardwareController Architecture

### Proposed Class Hierarchy

```
BaseController (abstract)
├── SimController (existing)
│   ├── Transport: TCP sockets (ports 8787, 8789)
│   ├── Process: subprocess.Popen for micropython_unix
│   └── GUI: TCPSocket on port 8787
│
└── HardwareController (new)
    ├── Transport: UART3 VCP via pyserial (/dev/ttyACM0)
    ├── Lifecycle: ST-Link (st-flash for flash/reset, OpenOCD for memory)
    └── GUI: Not available (physical buttons/touch)
```

### BaseController Interface

Based on analysis of `controller.py:41-95`:

```python
class BaseController:
    """Abstract interface for device controllers."""
    
    def start(self) -> None:
        """Initialize device and communication channels."""
        raise NotImplementedError
    
    def load(self) -> None:
        """Load initial state (unlock PIN, enter recovery, etc.)."""
        raise NotImplementedError
    
    def query(self, data: bytes, commands: list = []) -> bytes:
        """
        Send command and receive response.
        
        Protocol (from controller.py:83-95):
        1. Ensure data ends with \r\n
        2. Send to device
        3. Wait for ACK\r\n
        4. Optionally handle GUI confirmations
        5. Return response (stripped)
        """
        raise NotImplementedError
    
    def shutdown(self) -> None:
        """Clean up resources and stop device."""
        raise NotImplementedError
```

### SimController Implementation (Reference)

From `controller.py:41-95`:

| Method | Lines | Implementation Details |
|--------|-------|------------------------|
| `__init__` | 42-49 | Clears `./fs/` directory, initializes None |
| `start` | 51-56 | Popen `micropython_unix simulator.py` |
| `load` | 58-70 | Creates TCPSocket on 8787, sends PIN/recovery |
| `shutdown` | 72-81 | Sends "quit", kills process group |
| `query` | 83-95 | Sends via USB socket, waits ACK, receives |

### HardwareController Implementation (New)

| Method | Implementation | Source Pattern |
|--------|----------------|----------------|
| `__init__` | Store VCP port path, serial config | New |
| `start` | Flash firmware via st-flash, reset device | `docs/llm_testing_guide.md:274-283` `SWDInterface.flash_firmware()` |
| `load` | Send TEST_PIN via UART3 VCP | `src/test_mode.py:282-354` `_cmd_pin()` |
| `shutdown` | Close serial port | New |
| `query` | Send via pyserial, wait ACK, receive | Pattern from `controller.py:83-95` |

---

## 3. ST-Link Role Evaluation

### ST-Link Capabilities on STM32F469-DISCO

The onboard ST-Link provides **two independent channels** over single mini-USB:

| Channel | Protocol | Device Path | Purpose |
|---------|----------|-------------|---------|
| **SWD** | Serial Wire Debug | OpenOCD/st-flash | Flash, reset, memory access |
| **VCP** | Virtual COM Port | `/dev/ttyACM0` | UART3 serial at 115200 baud |

### SWD Channel: Lifecycle Controller

From `docs/llm_testing_guide.md:260-364`:

| Operation | Tool | Command | Reference |
|-----------|------|---------|-----------|
| Flash firmware | st-flash | `st-flash --reset write <bin> 0x08000000` | Line 276 |
| Reset device | st-flash | `st-flash reset` | Line 285 |
| Erase flash | st-flash | `st-flash erase` | Line 290 |
| Read memory | OpenOCD | `mdw <addr> <count>` | Line 296-310 |
| Set breakpoint | OpenOCD | `bp <addr> 2 hw` | Line 313-329 |
| Read registers | OpenOCD | `reg` | Line 332-346 |

### VCP Channel: UART3 Serial Communication

From `docs/llm_testing_guide.md:99`:
- **Pins**: PB10 (TX), PB11 (RX)
- **Baud Rate**: 115200
- **Device**: `/dev/ttyACM0` (Linux), `/dev/tty.usbmodem*` (Mac)
- **Internally connected** to ST-Link VCP

### Why NOT Debug UART

From `src/platform.py:316`:
```python
stlk = pyb.UART("YB", 9600)
```

This is the **debug UART** at 9600 baud - NOT suitable for HIL testing:
- Too slow (9600 vs 115200)
- Used for bootloader/recovery debug output
- Not exposed via ST-Link VCP

We use **UART3 at 115200 baud** instead (PB10/PB11 → ST-Link VCP).

### ST-Link Role Summary

| Role | Channel | Tool | When Used |
|------|---------|------|-----------|
| **Flashing** | SWD | st-flash | Before test session |
| **Reset** | SWD | st-flash | Between tests |
| **Memory Debug** | SWD | OpenOCD | When VCP unavailable/crashed |
| **Test Communication** | VCP (UART3) | pyserial | During all tests |

---

## 4. Options Comparison

### Communication Channel Options

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. ST-Link Mailbox** | Memory-mapped communication via SWD | No firmware changes needed | Slow (OpenOCD overhead), no async, complex sync |
| **B. Serial/USB VCP** | UART3 at 115200 via ST-Link VCP | Fast, simple, reliable, existing patterns | Requires firmware TestMode |
| **C. Raw REPL** | MicroPython raw REPL over serial | Interactive debugging | Blocks main loop, not suitable for async tests |
| **D. Hybrid (Chosen)** | VCP for commands + SWD for lifecycle/debug | Best of both worlds | Two toolchains to manage |

### Detailed Analysis

#### Option A: ST-Link Mailbox

```
Host (OpenOCD) ←→ SWD ←→ RAM mailbox ←→ Firmware polls RAM
```

| Aspect | Evaluation |
|--------|------------|
| Speed | Slow - OpenOCD subprocess spawn per transaction |
| Latency | 100-500ms per memory read/write |
| Complexity | High - memory barriers, polling, synchronization |
| Firmware Impact | Moderate - polling loop required |
| Debug Value | High - works even when firmware hangs |

#### Option B: Serial/USB VCP (UART3)

```
Host (pyserial) ←→ VCP ←→ UART3 (PB10/PB11) ←→ Firmware TestMode
```

| Aspect | Evaluation |
|--------|------------|
| Speed | Fast - 115200 baud, ~11KB/s |
| Latency | Low - ms range |
| Complexity | Low - standard serial I/O |
| Firmware Impact | Moderate - TestMode command loop |
| Debug Value | Medium - requires firmware running |

Pattern from `docs/llm_testing_guide.md:147-256`:
- `VCPReader` class with `read_line()`, `wait_for()`, `wait_for_marker()`
- Firmware uses `UART(3, 115200)` and writes timestamped log messages

#### Option C: Raw REPL

```
Host (pyserial) ←→ VCP ←→ UART ←→ MicroPython REPL
```

| Aspect | Evaluation |
|--------|------------|
| Speed | Fast |
| Latency | Low |
| Complexity | Low |
| Firmware Impact | High - blocks async event loop |
| Debug Value | High - interactive |

**Rejected**: Specter-DIY uses async/await pattern (see `test_mode.py:63-102`), REPL blocks event loop.

#### Option D: Hybrid (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│                    HardwareController                        │
├─────────────────────────────────────────────────────────────┤
│  VCP Interface (pyserial)    SWD Interface (st-flash/OCD)  │
│  ├── query() commands        ├── flash_firmware()          │
│  ├── wait_for_marker()       ├── reset_device()            │
│  └── read_line()             └── read_memory() (fallback)  │
└─────────────────────────────────────────────────────────────┘
```

| Aspect | Evaluation |
|--------|------------|
| Speed | Fast for commands, slow for lifecycle |
| Latency | Low for test communication |
| Complexity | Medium - two interfaces |
| Firmware Impact | Moderate - TestMode only |
| Debug Value | Highest - VCP + memory markers |

### Decision: Hybrid Approach

**Rationale**: Aligns with existing patterns in `docs/llm_testing_guide.md`, provides fallback debugging, minimal firmware changes.

---

## 5. Architecture Recommendation

### Recommended: Hybrid VCP + SWD Architecture

This architecture extends the patterns established in `docs/llm_testing_guide.md` with Specter-DIY's existing test infrastructure.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TEST RUNNER (Host)                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────┐    ┌──────────────────────┐                   │
│  │   HardwareController │    │   SimController      │                   │
│  │   (new)              │    │   (existing)         │                   │
│  ├──────────────────────┤    ├──────────────────────┤                   │
│  │ • VCPInterface       │    │ • TCPSocket (8789)   │                   │
│  │ • SWDInterface       │    │ • TCPSocket (8787)   │                   │
│  │ • LifecycleManager   │    │ • subprocess.Popen   │                   │
│  └──────────┬───────────┘    └──────────┬───────────┘                   │
│             │                           │                                │
│             └───────────┬───────────────┘                                │
│                         │                                                │
│              BaseController (interface)                                  │
│                         │                                                │
├─────────────────────────┼────────────────────────────────────────────────┤
│                         │                                                │
│  ┌──────────────────────▼──────────────────────┐                        │
│  │              test_basic.py                   │                        │
│  │  (unchanged - uses controller.query())       │                        │
│  └──────────────────────────────────────────────┘                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ mini-USB
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      STM32F469-DISCO + Shield-Lite                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐      │
│  │   ST-Link       │    │   STM32F469     │    │  Shield-Lite    │      │
│  │   (onboard)     │    │   MCU           │    │  Smartcard      │      │
│  ├─────────────────┤    ├─────────────────┤    ├─────────────────┤      │
│  │ • SWD           │◄──►│ • UART3 (VCP)   │    │ • PA2 (IO)      │      │
│  │ • VCP           │    │ • TestMode      │◄──►│ • PA4 (CLK)     │      │
│  │                 │    │ • USBHost       │    │ • PG10 (RST)    │      │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Mapping

| Host Component | Firmware Component | Protocol | File Reference |
|----------------|-------------------|----------|----------------|
| `VCPInterface` | `TestMode._command_loop()` | Text commands | `src/test_mode.py:63-102` |
| `SWDInterface` | N/A (hardware) | SWD | `docs/llm_testing_guide.md:260-364` |
| `HardwareController.query()` | `TestMode._process_command()` | TEST_* commands | `src/test_mode.py:103-150` |

### Data Flow

```
1. Flash/Reset (SWD):
   st-flash write firmware.bin 0x08000000
   
2. Boot & Initialize:
   Firmware starts → TestMode._command_loop() starts polling stdin
   
3. Test Command (VCP):
   Host → pyserial write "TEST_PIN:1234\r\n"
   → UART3 receives → TestMode parses → _cmd_pin() executes
   → Response "OK:PIN verified\r\n" → UART3 transmits → pyserial reads
   
4. Debug Fallback (SWD):
   If VCP hangs → OpenOCD read memory markers at 0x20002000
```

### Alignment with Existing Guide

This architecture directly implements patterns from `docs/llm_testing_guide.md`:

| Guide Pattern | HIL Implementation |
|---------------|-------------------|
| `VCPReader` (lines 202-256) | `VCPInterface` class |
| `SWDInterface` (lines 270-364) | `SWDInterface` class |
| `MarkerReader` (lines 443-518) | Memory marker fallback |
| `HardwareTestRig` (lines 545-679) | `HardwareController` class |

---

## 6. Controller Interface Mapping

### SimController.query() Analysis

From `test/integration/util/controller.py:83-95`:

```python
def query(self, data, commands=[]):
    if isinstance(data, str):
        data = data.encode()
    if data[-1:] not in b"\r\n":
        data = data + b"\r\n"
    res = self.usb.query(data)           # 1. Send to USB socket
    assert res == b"ACK\r\n"             # 2. Expect ACK
    # if we need to confirm anything
    for command in commands:
        sim.gui.send(command)            # 3. GUI confirmations
        time.sleep(0.3)
    res = sim.usb.receive()              # 4. Receive response
    return res.strip()                   # 5. Strip and return
```

### HardwareController.query() Mapping

| SimController Step | HardwareController Equivalent | Implementation |
|--------------------|-------------------------------|----------------|
| `self.usb.query(data)` | VCP serial write | `self.vcp.write(data)` |
| `assert res == b"ACK\r\n"` | VCP read until ACK | `self._wait_ack(timeout=5.0)` |
| `sim.gui.send(command)` | **NOT AVAILABLE** | TestMode handles internally |
| `sim.usb.receive()` | VCP read until EOL | `self.vcp.read_until(b"\r\n")` |
| `return res.strip()` | Same | `return res.strip()` |

### Protocol Differences

| Aspect | SimController | HardwareController |
|--------|---------------|-------------------|
| Transport | TCP socket (port 8789) | UART3 VCP (115200 baud) |
| ACK Source | `src/hosts/usb.py:15` `ACK = b"ACK\r\n"` | Same protocol |
| GUI Confirmations | TCP to port 8787 | Use TEST_* commands |
| Timeout | None (blocking) | Required (serial may hang) |

### Method Signature Mapping

```python
# SimController (controller.py:83)
def query(self, data, commands=[]) -> bytes:
    ...

# HardwareController (new)
def query(self, data: bytes, timeout: float = 10.0) -> bytes:
    """
    Send command via UART3 VCP and receive response.
    
    Unlike SimController, GUI confirmations are handled by
    TestMode commands (TEST_UI_SET, TEST_UI_PIN) sent in data.
    
    Args:
        data: Command bytes (will append \r\n if missing)
        timeout: Max seconds to wait for response
        
    Returns:
        Response bytes (stripped)
        
    Raises:
        TimeoutError: If no response within timeout
        SerialException: If VCP communication fails
    """
    ...
```

### Test Compatibility

Tests in `test/integration/tests/test_basic.py` use `sim.query()`:

```python
# Line 11
res = sim.query(b"sign "+unsigned, [True])

# Line 23
res = sim.query(b"fingerprint")
```

With `BaseController` interface, tests can switch between:

```python
# Simulator (existing)
from util.controller import sim
controller = sim

# Hardware (new)
from util.hardware_controller import HardwareController
controller = HardwareController(port='/dev/ttyACM0')
```

---

## 7. On-Device Test Agent

### TestMode Command Set

From `src/test_mode.py:1-24` and implementation at lines 103-651:

| Command | Format | Handler | Lines | Description |
|---------|--------|---------|-------|-------------|
| `TEST_PIN` | `TEST_PIN:1234` | `_cmd_pin()` | 282-354 | Unlock with PIN |
| `TEST_XPUB` | `TEST_XPUB:m/84h/0h/0h` | `_cmd_xpub()` | 355-372 | Get XPUB at derivation path |
| `TEST_SIGN` | `TEST_SIGN:<hex_sighash>` | `_cmd_sign()` | 373-395 | Sign 32-byte sighash |
| `TEST_SIGN_AT` | `TEST_SIGN_AT:<path>:<hash>` | `_cmd_sign_at()` | 396-423 | Sign at explicit path |
| `TEST_SET_NETWORK` | `TEST_SET_NETWORK:<net>` | `_cmd_set_network()` | 424-437 | Set network (main/test/signet/regtest) |
| `TEST_GET_ADDRESS` | `TEST_GET_ADDRESS:<path>` | `_cmd_get_address()` | 452-535 | Get address at path |
| `TEST_FULL_CHECK` | `TEST_FULL_CHECK` | `_cmd_full_check()` | 538-651 | Comprehensive verification |
| `TEST_STATUS` | `TEST_STATUS` | `_cmd_status()` | 156-167 | Get current status |
| `TEST_BOOT_STATE` | `TEST_BOOT_STATE` | `_cmd_boot_state()` | 168-182 | Detailed boot state |
| `TEST_WAIT_READY` | `TEST_WAIT_READY` | `_cmd_wait_ready()` | 184-196 | Wait for keystore ready |
| `TEST_WALLET_SMOKE` | `TEST_WALLET_SMOKE` | `_cmd_wallet_smoke()` | 197-221 | AEAD roundtrip test |
| `TEST_SCREEN` | `TEST_SCREEN` | `_cmd_screen()` | 222-240 | Get active GUI screen |
| `TEST_UI_SET` | `TEST_UI_SET:<value>` | `_cmd_ui_set()` | 242-260 | Set screen value |
| `TEST_UI_PIN` | `TEST_UI_PIN:<digits>` | `_cmd_ui_pin()` | 262-280 | Enter PIN on PinScreen |
| `TEST_RESET` | `TEST_RESET` | `_cmd_reset()` | 439-451 | Reset connection |

### Response Format

From `src/test_mode.py:152-154`:

```python
def _respond(self, msg):
    """Send response."""
    print("[TestMode] RESP:", msg)
```

All responses follow:
- **Success**: `OK:<data>`
- **Error**: `ERROR:<message>`

### Command Loop Architecture

From `src/test_mode.py:63-102`:

```python
async def _command_loop(self):
    """Main command processing loop - called from Specter.setup()."""
    self.running = True
    buffer = ""
    
    while self.running:
        # Poll stdin using uselect (MicroPython)
        poller = select.poll()
        poller.register(sys.stdin, select.POLLIN)
        
        result = poller.poll(100)
        if result:
            char = sys.stdin.read(1)
            if char == '\n' or char == '\r':
                if buffer.strip().startswith('TEST_'):
                    await self._process_command(buffer.strip())
                buffer = ""
            else:
                buffer += char
        else:
            await asyncio.sleep_ms(50)
```

### Keystore Support

From `src/test_mode.py:36-49`:

| Keystore Type | Supported Commands | Notes |
|---------------|-------------------|-------|
| **Satochip** | All commands | Full XPUB, signing, address support |
| **SeedKeeper** | PIN, AEAD, status | No XPUB/signing (seed storage only) |
| **MemoryCard** | PIN, AEAD, status | No XPUB/signing |

### Integration with HardwareController

| HardwareController Method | TestMode Command | Purpose |
|---------------------------|------------------|---------|
| `unlock(pin)` | `TEST_PIN:<pin>` | Authenticate to smartcard |
| `get_xpub(path)` | `TEST_XPUB:<path>` | Derive XPUB |
| `sign(hash)` | `TEST_SIGN:<hash>` | Sign sighash |
| `get_address(path)` | `TEST_GET_ADDRESS:<path>` | Get address |
| `wait_ready()` | `TEST_WAIT_READY` | Block until keystore ready |
| `check_status()` | `TEST_STATUS` | Get current state |

---

## 8. Real Hardware Testing

### Smart Card Testing Considerations

#### Card Presence Detection

From `src/test_mode.py:162`:
```python
"card_inserted": ks.connection.isCardInserted() if ks else False
```

Hardware tests must:
1. Wait for card insertion before PIN commands
2. Handle card removal during tests
3. Reset connection state on card change

#### Reset Timing

From `src/test_mode.py:439-451`:
```python
async def _cmd_reset(self):
    """Reset connection."""
    ks = self.find_javacard_keystore()
    if ks:
        ks.connection.disconnect()
        ks.connected = False
        ks._pin_unlocked = False
        self._respond("OK:Reset")
```

Hardware-specific timing:
- Card reset: 50-100ms for electrical stabilization
- Applet selection: 100-200ms
- Secure channel: 200-500ms
- Total initialization: 500-1000ms

#### Peripheral Initialization Sequence

From `docs/llm_testing_guide.md:97-101`:

| Function | Pins | Notes |
|----------|------|-------|
| Smartcard | PA2 (IO), PA4 (CLK), PG10 (RST), PC2 (Presence), PC5 (Power) | USART2 smartcard mode |
| Debug (SWD) | PA13 (SWDIO), PA14 (SWCLK) | ST-Link debugger |
| UART3 (VCP) | PB10 (TX), PB11 (RX) | Internally connected to ST-Link VCP |

### Test Isolation Requirements

| Requirement | Implementation |
|-------------|----------------|
| Flash wipe between tests | `st-flash erase` before each test class |
| Keystore reset | `TEST_RESET` command |
| Network isolation | `TEST_SET_NETWORK:regtest` |
| State verification | `TEST_FULL_CHECK` before critical tests |

### Hardware Test Patterns

#### Pattern 1: Card Lifecycle Test

```python
def test_card_lifecycle(controller):
    controller.flash("bin/firmware.bin")
    controller.reset()
    
    # Wait for boot
    assert controller.query("TEST_WAIT_READY") == b"OK:ready"
    
    # Check no card
    status = controller.query("TEST_STATUS")
    assert "card_inserted': False" in status.decode()
    
    # Insert card (physical action or automated reader)
    # ... hardware-specific ...
    
    # Verify card detected
    status = controller.query("TEST_STATUS")
    assert "card_inserted': True" in status.decode()
    
    # Unlock
    result = controller.query("TEST_PIN:123456")
    assert result.startswith(b"OK:")
```

#### Pattern 2: Signing Test

```python
def test_sign_hash(controller):
    # Assumes card unlocked
    sighash = "00" * 32  # 32-byte test hash
    
    result = controller.query(f"TEST_SIGN:{sighash}")
    assert result.startswith(b"OK:")
    
    # Verify signature length (DER format, variable 70-72 bytes)
    sig_hex = result.decode().replace("OK:", "")
    assert 140 <= len(sig_hex) <= 144  # hex encoding doubles length
```

#### Pattern 3: Memory Marker Fallback

From `docs/llm_testing_guide.md:368-434`:

```python
def test_with_memory_markers(controller):
    try:
        result = controller.query("TEST_STATUS", timeout=5.0)
    except TimeoutError:
        # VCP hung - use SWD memory markers
        markers = controller.read_memory_markers()
        if markers['is_error']:
            raise AssertionError(f"Firmware error: {markers}")
        else:
            raise AssertionError("VCP timeout without error marker")
```

---

## 9. Incremental Migration Path

### Phase 1: Foundation (Week 1-2)

**Goal**: Establish VCP communication with TestMode

| Task | Dependencies | Deliverable |
|------|--------------|-------------|
| Create `HardwareController` class | None | `test/integration/util/hardware_controller.py` |
| Implement VCPInterface | pyserial | Serial read/write with ACK protocol |
| Map `query()` to TestMode commands | VCPInterface | `query("TEST_STATUS")` works |
| Add pytest fixture | HardwareController | `@pytest.fixture def hardware_controller()` |

**Verification**: 
```bash
python -c "from util.hardware_controller import HardwareController; c = HardwareController(); print(c.query('TEST_STATUS'))"
# Expected: b"OK:{...}"
```

### Phase 2: Lifecycle Management (Week 2-3)

**Goal**: Automated flash/reset workflow

| Task | Dependencies | Deliverable |
|------|--------------|-------------|
| Implement SWDInterface | stlink-tools, OpenOCD | Flash, reset, memory read |
| Add LifecycleManager | SWDInterface | `flash()`, `reset()`, `erase()` |
| Integrate with HardwareController | LifecycleManager | Auto-flash before test session |
| Add memory marker reader | SWDInterface | `read_markers()` for crash debug |

**Verification**:
```bash
python -c "from util.hardware_controller import HardwareController; c = HardwareController(); c.flash('bin/firmware.bin'); c.reset()"
# Expected: Device boots, VCP responsive
```

### Phase 3: Test Migration (Week 3-4)

**Goal**: Run existing tests on hardware

| Task | Dependencies | Deliverable |
|------|--------------|-------------|
| Create BaseController interface | None | Abstract class in `test/integration/util/base_controller.py` |
| Refactor SimController | BaseController | Inherits from BaseController |
| Add test parametrization | BaseController | Tests run with `--hardware` flag |
| Handle GUI command differences | TestMode | TEST_UI_SET replaces GUI socket |

**Verification**:
```bash
pytest test/integration/tests/test_basic.py --controller=simulator  # Existing
pytest test/integration/tests/test_basic.py --controller=hardware   # New
```

### Phase 4: Smart Card Tests (Week 4-5)

**Goal**: Full smart card testing suite

| Task | Dependencies | Deliverable |
|------|--------------|-------------|
| Add card detection tests | HardwareController | Test card presence/absence |
| Add PIN verification tests | TestMode TEST_PIN | Valid/invalid PIN scenarios |
| Add XPUB derivation tests | TestMode TEST_XPUB | Path derivation verification |
| Add signing tests | TestMode TEST_SIGN | Signature verification |
| Add AEAD storage tests | TestMode TEST_WALLET_SMOKE | Encrypted storage |

**Verification**:
```bash
pytest test/integration/tests/test_smartcard.py --controller=hardware -v
# All tests pass with real SeedKeeper/Satochip card
```

### Migration Dependencies

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
   │            │            │            │
   │            │            │            └── Smart card tests
   │            │            └── Test parametrization
   │            └── Lifecycle management
   └── VCP communication
```

### Backward Compatibility

| Component | Change | Compatibility |
|-----------|--------|---------------|
| `SimController` | Inherits BaseController | 100% API compatible |
| `test_basic.py` | Parametrized controller | No changes required |
| `controller.py` | New file alongside | Existing imports work |

---

## 10. Risks and Mitigations

### Risk 1: UART3 VCP Reliability

| Aspect | Details |
|--------|---------|
| **Risk** | VCP may drop bytes or hang under load |
| **Likelihood** | Medium |
| **Impact** | High - test failures, false negatives |
| **Symptoms** | Timeout waiting for ACK, truncated responses |

**Mitigations**:
1. **Acknowledge protocol**: Every command gets `ACK\r\n` response (from `src/hosts/usb.py:15`)
2. **Timeout handling**: All VCP reads have configurable timeout (default 10s)
3. **Memory marker fallback**: When VCP hangs, use SWD to read markers at `0x20002000`
4. **Retry logic**: Implement exponential backoff for transient failures

**Implementation** (from `docs/llm_testing_guide.md:221-231`):
```python
def wait_for(self, marker, timeout=10.0):
    """Wait for specific marker in output with timeout."""
    start = time.time()
    while time.time() - start < timeout:
        line = self.read_line(timeout=1.0)
        if line and marker in line:
            return True, line
    return False, None
```

### Risk 2: Timing Differences

| Aspect | Details |
|--------|---------|
| **Risk** | Hardware timing differs from simulator |
| **Likelihood** | High |
| **Impact** | Medium - flaky tests |
| **Examples** | Card insertion detection, secure channel setup |

**Mitigations**:
1. **`TEST_WAIT_READY`**: Block until keystore ready (from `test_mode.py:184-196`, 30s timeout)
2. **Configurable timeouts**: All operations have generous defaults
3. **Status checks**: Use `TEST_STATUS` and `TEST_BOOT_STATE` before assertions
4. **Timing profiles**: Separate timeout configs for simulator vs hardware

**Timing Reference**:
| Operation | Simulator | Hardware |
|-----------|-----------|----------|
| Boot to ready | <1s | 2-5s |
| Card detection | Instant | 50-200ms |
| PIN verify | <100ms | 500-2000ms |
| XPUB derive | <100ms | 200-500ms |
| Sign hash | <100ms | 500-2000ms |

### Risk 3: Test Isolation

| Aspect | Details |
|--------|---------|
| **Risk** | Tests affect each other via shared state |
| **Likelihood** | Medium |
| **Impact** | High - cascading failures |
| **Examples** | Unlocked keystore persists, dirty flash |

**Mitigations**:
1. **`TEST_RESET`**: Reset connection state between tests (`test_mode.py:439-451`)
2. **Flash erase**: `st-flash erase` before test class
3. **Test ordering**: Independent tests first, stateful tests isolated
4. **Fixture scoping**: `scope="function"` for isolation, `scope="session"` for expensive setup

### Risk 4: ST-Link / OpenOCD Compatibility

| Aspect | Details |
|--------|---------|
| **Risk** | ST-Link firmware or OpenOCD version incompatibility |
| **Likelihood** | Low |
| **Impact** | High - cannot flash or debug |
| **Examples** | ST-Link v2 vs v3, OpenOCD config changes |

**Mitigations**:
1. **Version pinning**: Document tested versions
2. **st-flash primary**: Use st-flash for flash/reset (more stable than OpenOCD)
3. **OpenOCD fallback only**: Use OpenOCD only for memory reads when VCP fails
4. **Config validation**: Verify ST-Link connection before tests

**Tested Versions** (from `docs/llm_testing_guide.md:130-142`):
```bash
st-info --version   # stlink-tools 1.7.0+
openocd --version   # OpenOCD 0.11.0+
```

### Risk 5: Smart Card State

| Aspect | Details |
|--------|---------|
| **Risk** | Card state persists across tests (locked, wrong PIN counter) |
| **Likelihood** | Medium |
| **Impact** | High - card may be permanently locked |
| **Examples** | Too many wrong PIN attempts |

**Mitigations**:
1. **Known PIN**: Always use test PIN (e.g., "123456")
2. **PIN counter monitoring**: Check remaining attempts via `TEST_STATUS`
3. **Test card separation**: Dedicated test cards, never production cards
4. **Factory reset procedure**: Document card reset/recovery

### Risk Summary Matrix

| Risk | Likelihood | Impact | Priority | Mitigation Status |
|------|------------|--------|----------|-------------------|
| VCP reliability | Medium | High | P1 | ACK protocol + memory markers |
| Timing differences | High | Medium | P1 | TEST_WAIT_READY + configurable timeouts |
| Test isolation | Medium | High | P1 | TEST_RESET + flash erase |
| ST-Link compatibility | Low | High | P2 | Version pinning + st-flash primary |
| Smart card state | Medium | High | P2 | Known PIN + test card separation |

---

## Appendix A: File Reference Index

### Core Test Infrastructure

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `test/integration/util/controller.py` | Simulator controller | `TCPSocket`, `SimController`, `BitcoinCore` |
| `test/integration/tests/test_basic.py` | Integration tests | `BasicTest` class |

### Firmware Components

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `src/test_mode.py` | On-device test agent | `TestMode` class, all `TEST_*` handlers |
| `src/platform.py` | Platform abstraction | `stlk` UART (debug), `reboot()`, `wipe()` |
| `src/hosts/usb.py` | USB host communication | `USBHost`, `ACK` protocol |
| `src/gui/tcp_gui.py` | Simulator GUI | `TCPGUI`, JSON command protocol |

### Documentation

| File | Purpose | Key Sections |
|------|---------|--------------|
| `docs/llm_testing_guide.md` | Hardware testing guide | VCPReader, SWDInterface, MarkerReader, HardwareTestRig |

---

## Appendix B: Command Quick Reference

### TestMode Commands

```bash
# Status and diagnostics
TEST_STATUS                    # Get current keystore status
TEST_BOOT_STATE                # Detailed boot state
TEST_WAIT_READY                # Block until ready (30s timeout)
TEST_FULL_CHECK                # Comprehensive verification

# Authentication
TEST_PIN:123456                # Unlock with PIN
TEST_RESET                     # Reset connection

# Key operations (Satochip only)
TEST_XPUB:m/84h/0h/0h          # Get XPUB at path
TEST_SIGN:<hex_hash>           # Sign 32-byte hash
TEST_SIGN_AT:m/84h/0h/0h/0/0:<hex_hash>  # Sign at path
TEST_GET_ADDRESS:m/84h/0h/0h/0/0  # Get address

# Network
TEST_SET_NETWORK:regtest       # Set network

# GUI interaction
TEST_SCREEN                    # Get active screen
TEST_UI_SET:value              # Set screen value
TEST_UI_PIN:1234               # Enter PIN on screen

# Storage
TEST_WALLET_SMOKE              # AEAD roundtrip test
```

### SWD Commands

```bash
# Flash operations
st-flash write firmware.bin 0x08000000   # Flash firmware
st-flash reset                           # Reset device
st-flash erase                           # Erase flash

# Debug operations
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
    -c "init; halt; mdw 0x20002000 4; shutdown"  # Read memory markers
```

### VCP Serial

```bash
# Connect to VCP
screen /dev/ttyACM0 115200

# Or with pyserial
python -c "import serial; s=serial.Serial('/dev/ttyACM0', 115200); ..."

## Current Status (Task 11)

### File Path Verification

| File Path | Status | Notes |
|-----------|--------|-------|
| src/gui/tcp_gui.py | ✓ Implemented | TCP GUI for simulator |
| src/hosts/usb.py | ✓ Implemented | USB host communication |
| src/platform.py | ✓ Implemented | Platform abstraction |
| src/test_mode.py | ✓ Implemented | TestMode command loop |
| test/integration/tests/test_basic.py | ✓ Implemented | Basic integration tests |
| test/integration/util/controller.py | ✓ Implemented | SimController with TCPSocket |
| test/integration/util/hardware_controller.py | ✓ Implemented | HardwareController (new) |
| test/integration/util/base_controller.py | ✗ Path Fixed | Was referenced as util/base_controller.py (incorrect) |
| test/integration/tests/test_smartcard.py | ✗ Not Implemented | Smart card tests pending |

### Issues Found

1. **Incorrect file path**: `util/base_controller.py` should be `test/integration/util/base_controller.py`
2. **Missing implementation**: `test/integration/tests/test_smartcard.py` was not created (mentioned in Phase 4 of migration path)

### Next Steps

- Update file path reference in documentation
- Create test_smartcard.py if Phase 4 of migration path is to be completed
- Verify all file paths match implementation in Tasks 2-9
