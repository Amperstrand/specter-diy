# HIL Testing Architecture for Specter-DIY

## TL;DR

> **Quick Summary**: Implement hardware-in-the-loop testing for Specter-DIY by extending the existing TestMode agent to listen on UART3 VCP (115200 baud, PB10/PB11 → ST-Link VCP → /dev/ttyACM0), creating a HardwareController that implements the same `query(data, commands=[])` interface as SimController, and writing an architecture document that captures the complete design rationale. Aligns with existing patterns in `docs/llm_testing_guide.md`.
> 
> **Deliverables**:
> - Architecture document (`.sisyphus/docs/hil-architecture.md`) with all 10 requested sections
> - `BaseController` ABC extracted from SimController pattern
> - `HardwareController` class implementing the controller interface over UART3 VCP at 115200 baud
> - Extended `TestMode` with UART3 VCP channel support on-device
> - `STLinkManager` for lifecycle operations (flash/reset via st-flash, memory reads via OpenOCD)
> - Updated test runner supporting `--hardware` flag
> - Makefile targets for HIL testing
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Architecture Doc → BaseController ABC → TestMode UART Extension → HardwareController → Test Runner Integration → Final Verification

---

## Context

### Original Request
Design and implement a hardware-in-the-loop (HIL) testing system for Specter-DIY (MicroPython on STM32) that reuses the existing simulator test architecture. The user wants to run the current integration tests against real physical hardware while preserving the existing host-side test API.

### Interview Summary
**Key Discussions**:
- **Architecture direction**: Hybrid — ST-Link SWD for lifecycle (flash/reset via st-flash) + UART3 VCP for control channel at 115200 baud
- **UART config**: Use UART3 (PB10/PB11) at 115200 baud — internally connected to ST-Link VCP, appears as /dev/ttyACM0. NOT the debug UART (`pyb.UART("YB", 9600)` from platform.py:316 which is a different channel).
- **Reset strategy**: Software reset by default (fast), ST-Link hard reset on demand (for peripheral state tests)
- **Deliverable scope**: Full implementation + architecture document, not just documentation
- **Firmware type**: Dedicated debug/test firmware, not production

**Research Findings**:
- `TestMode` (src/test_mode.py, 652 lines) is already 80% of an on-device test agent — has command/response protocol but only listens on stdin
- ST-Link UART3 VCP at 115200 baud: `UART(3, 115200)` on PB10/PB11, internally connected to ST-Link VCP, appears as `/dev/ttyACM0` on host. NOT `pyb.UART("YB", 9600)` from `src/platform.py:316` — that's the debug UART.
- `SimController.query(data, commands=[])` is the ONLY interface all integration tests use — clean abstraction point
- SimController uses two TCP channels (GUI + USB); HardwareController collapses these into one UART3 VCP channel via TestMode commands
- Integration tests are pure `unittest.TestCase` — no framework-specific coupling

### Metis Review
**Identified Gaps** (addressed):
- **Scope ambiguity (doc vs implementation)**: Resolved — both: architecture doc + working code
- **UART channel**: Resolved — use UART3 VCP at 115200 (per `docs/llm_testing_guide.md`), NOT the debug UART at 9600. Faster and correct VCP path.
- **Reset strategy**: Resolved — software default + hard reset on demand
- **Test coverage target**: Defaulted to 100% compatibility for test_basic.py, best-effort for test_with_rpc.py
- **Hardware failure recovery**: Addressed via timeout/retry in HardwareController + hard reset fallback
- **Test isolation**: Addressed via software reset between tests + optional hard reset

---

## Work Objectives

### Core Objective
Build a complete HIL testing backend that allows running existing Specter-DIY integration tests against real STM32 hardware, using a HardwareController that speaks the same `query(data, commands=[])` interface as the existing SimController.

### Concrete Deliverables
- `docs/hil-architecture.md` — Comprehensive architecture document with all 10 requested sections
- `test/integration/util/base_controller.py` — Abstract `BaseController` class extracted from SimController pattern
- `test/integration/util/hardware_controller.py` — `HardwareController` + `STLinkManager` + `UARTChannel` (aligned with VCPReader/SWDInterface patterns from `docs/llm_testing_guide.md`)
- `src/test_mode.py` (modified) — Extended TestMode that also listens on UART3 VCP at 115200 baud
- `test/integration/util/controller.py` (modified) — SimController extends BaseController
- `test/integration/run_tests.py` (modified) — Supports `--hardware` / `--target` flags
- `Makefile` (modified) — New `test-hil` target

### Definition of Done
- [ ] `python3 run_tests.py --hardware --port /dev/ttyACM0` runs test_basic.py against real device
- [ ] `python3 run_tests.py` still runs all tests against simulator (no regression)
- [ ] Architecture document covers all 10 requested sections with codebase references
- [ ] TestMode on device responds to commands over both stdin AND UART3 VCP

### Must Have
- HardwareController implements identical `query(data, commands=[])` interface as SimController
- TestMode extended with UART3 VCP listener (not a new agent)
- Existing tests run unmodified against either backend
- Architecture document with transport analysis, options comparison, and migration path
- Software reset between tests by default
- Hard reset on demand via st-flash reset
- Timeout/retry handling for hardware communication failures

### Must NOT Have (Guardrails)
- MUST NOT modify existing test files (test_basic.py, test_with_rpc.py) — they must work as-is
- MUST NOT use the debug UART (`pyb.UART("YB", 9600)` from platform.py) — use UART3 VCP at 115200 instead
- MUST NOT add CI/CD integration (out of scope)
- MUST NOT support multi-device testing (out of scope)
- MUST NOT create a separate testing framework — extend existing patterns
- MUST NOT add external dependencies beyond pyserial and stlink-tools/OpenOCD (already assumed available)
- MUST NOT over-abstract: keep it simple, one controller per backend
- MUST NOT add excessive error handling or retry logic — keep it pragmatic

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES — `test/integration/` has unittest-based integration tests
- **Automated tests**: YES (Tests-after) — test the new infrastructure with the existing test suite
- **Framework**: unittest (existing) + pytest optional for new controller tests

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Host-side Python**: Use Bash — run Python scripts, import modules, verify interfaces
- **Architecture doc**: Use Bash — verify all referenced files exist, grep for referenced symbols
- **Controller interface**: Use Bash — run existing tests with `--hardware` flag against simulator (mock hardware for CI)
- **Firmware changes**: Use Bash — build with `make unix`, verify TestMode accepts UART input in simulator mode

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation):
├── Task 1: Architecture document (all 10 sections) [deep]
├── Task 2: BaseController ABC extraction [quick]
└── Task 3: STLinkManager lifecycle module [unspecified-high]

Wave 2 (After Wave 1 — core implementation, PARALLEL):
├── Task 4: TestMode UART extension (firmware side) [deep]
├── Task 5: UARTChannel host-side communication [unspecified-high]
└── Task 6: Command protocol mapping (SimController → TestMode) [unspecified-high]

Wave 3 (After Wave 2 — integration):
├── Task 7: HardwareController assembly [deep]
├── Task 8: SimController refactor to extend BaseController [quick]
└── Task 9: Test runner --hardware flag + Makefile targets [quick]

Wave 4 (After Wave 3 — verification):
├── Task 10: Simulator-mode integration test (run existing tests through refactored controller) [unspecified-high]
└── Task 11: Documentation review + cross-reference verification [quick]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real QA — run full test suite through refactored SimController (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: Task 1 → Task 2 → Task 4,5,6 → Task 7 → Task 10 → F1-F4
Parallel Speedup: ~50% faster than sequential
Max Concurrent: 3 (Waves 1 & 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 (Architecture doc) | — | 4, 6, 7 | 1 |
| 2 (BaseController ABC) | — | 4, 5, 7, 8 | 1 |
| 3 (STLinkManager) | — | 7, 9 | 1 |
| 4 (TestMode UART) | 1, 2 | 7 | 2 |
| 5 (UARTChannel) | 2 | 7 | 2 |
| 6 (Command mapping) | 1 | 7 | 2 |
| 7 (HardwareController) | 2, 4, 5, 6 | 9, 10 | 3 |
| 8 (SimController refactor) | 2 | 10 | 3 |
| 9 (Test runner + Makefile) | 3, 7 | 10 | 3 |
| 10 (Integration test) | 7, 8, 9 | F1-F4 | 4 |
| 11 (Doc review) | 1 | F1-F4 | 4 |
| F1-F4 (Final verification) | 10, 11 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 3 tasks — T1 → `deep`, T2 → `quick`, T3 → `unspecified-high`
- **Wave 2**: 3 tasks — T4 → `deep`, T5 → `unspecified-high`, T6 → `unspecified-high`
- **Wave 3**: 3 tasks — T7 → `deep`, T8 → `quick`, T9 → `quick`
- **Wave 4**: 2 tasks — T10 → `unspecified-high`, T11 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

> Implementation + Test = ONE Task. Never separate.
> EVERY task MUST have: Recommended Agent Profile + Parallelization info + QA Scenarios.


- [x] 1. Architecture Document — All 10 Requested Sections

  **What to do**:
  - Create `docs/hil-architecture.md` with the comprehensive HIL testing architecture design
  - Section 1 — Transport Analysis: Classify every component in `test/integration/util/controller.py` as transport-specific or reusable. The `query(data, commands=[])` interface, test orchestration, and assertion patterns are reusable. `TCPSocket`, socket connection logic, and process management are transport-specific.
  - Section 2 — HardwareController Architecture: Describe the `BaseController` → `SimController` / `HardwareController` class hierarchy. Show how `HardwareController.query()` maps USB commands to `TEST_*` UART commands and GUI commands to `TEST_UI_*` UART commands.
  - Section 3 — ST-Link Role Evaluation: ST-Link serves as BOTH lifecycle controller (flash/reset via SWD debug interface through st-flash primarily, OpenOCD for memory reads) AND control channel carrier (UART3 VCP at 115200 baud routed through ST-Link's virtual COM port on PB10/PB11 to host as /dev/ttyACM0). Evaluate: primary channel (rejected — SWD is for debug, not data), lifecycle-only (rejected — wastes available VCP), hybrid (chosen — lifecycle via SWD + control via UART3 VCP).
  - Section 4 — Options Comparison Table: Compare ST-Link mailbox/memory poking (fragile, version-dependent, no standard protocol), serial/USB VCP (good bandwidth but separate cable, USB enumeration issues), raw REPL (flexible but parsing-heavy, no structured protocol), hybrid ST-Link lifecycle + UART control (chosen — single cable, structured protocol, existing infrastructure).
  - Section 5 — Architecture Recommendation: Hybrid with UART3 VCP at 115200 baud. Rationale: single cable (ST-Link provides both SWD and VCP), TestMode already exists, UART3 internally connected to ST-Link VCP, clean separation of lifecycle (SWD/st-flash) and control (UART3 VCP). Reference docs/llm_testing_guide.md for prior art.
  - Section 6 — Controller Interface Mapping: Show exact mapping from `SimController.query()` → `HardwareController.query()`. Map `sim.usb.query(data)` → `uart.send('TEST_SIGN:' + hex(data))`. Map `sim.gui.send(True)` → `uart.send('TEST_UI_SET:confirm')`. Map `sim.gui.send(json.dumps({...}))` → `uart.send('TEST_UI_SET:' + value)`. Include mapping table for all command types.
  - Section 7 — On-Device Test Agent: Document TestMode's existing command set and the UART extension. Show that TestMode already handles TEST_PIN, TEST_XPUB, TEST_SIGN, TEST_SCREEN, TEST_UI_SET, TEST_UI_PIN, TEST_RESET. The extension adds UART polling alongside stdin polling in the asyncio loop.
  - Section 8 — Real Hardware Testing: Explain how smart card testing works (TestMode has access to Specter instance which has keystore with card manager), how reset timing is tested (TEST_RESET + hard_reset via STLink), how peripheral init is tested (TEST_BOOT_STATE, TEST_STATUS report peripheral status).
  - Section 9 — Incremental Migration Path: Phase 1 (extract BaseController ABC, refactor SimController), Phase 2 (build UARTChannel + HardwareController), Phase 3 (extend TestMode with UART), Phase 4 (run existing tests against hardware).
  - Section 10 — Risks and Failure Modes: UART3 VCP at 115200 baud reliability (higher baud = faster but verify no data loss), timing differences (hardware slower than simulator), test isolation (state leakage between tests), smart card state management, st-flash/OpenOCD version compatibility. Note: docs/llm_testing_guide.md should be referenced as prior art throughout.
  - Include concrete file references throughout: exact file paths, line numbers, class names, method signatures

  **Must NOT do**:
  - MUST NOT be a generic testing overview — every statement must reference actual Specter-DIY code
  - MUST NOT propose changes to existing test files
  - MUST NOT include CI/CD integration design

  **Recommended Agent Profile**:
  > This is a deep synthesis task requiring understanding of both firmware and host-side code.
  - **Category**: `deep`
    - Reason: Requires synthesizing findings across 15+ analyzed files into a coherent architectural narrative
  - **Skills**: []
    - No special skills needed — all research is complete, this is pure writing/synthesis
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser interaction needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 4, 6, 7 (need architecture decisions documented)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py` — Full file: SimController class, TCPSocket class, query() method. This is THE interface to map.
  - `src/test_mode.py` — Full file: TestMode class, all TEST_* commands, stdin polling loop. This is the on-device agent to extend.
  - `src/platform.py:316` — `stlk = pyb.UART("YB", 9600)` — existing debug UART (NOT the VCP). Include in doc to clarify which UART is which and why we use UART3 VCP instead.
  - `src/hosts/usb.py` — USBHost class: command protocol with ACK/response pattern over USB VCP
  - `src/gui/tcp_gui.py` — TCPGUI class: JSON command protocol for GUI automation
  - `src/hosts/core.py` — Abstract Host base class with init/update/enable/disable pattern
  - `docs/llm_testing_guide.md` — Existing HIL testing guide with VCPReader, SWDInterface, MarkerReader, HardwareTestRig classes. PRIOR ART — architecture doc should reference and align with these patterns.

  **API/Type References**:
  - `src/specter.py` — Specter class: setup(), event loop, how TestMode is initialized
  - `src/main.py` — Entry point: how TCPGUI vs SpecterGUI is selected based on platform.simulator

  **Test References**:
  - `test/integration/tests/test_basic.py` — How tests use sim.query(data, commands=[]). Representative test patterns.
  - `test/integration/tests/test_with_rpc.py` — Bitcoin Core RPC integration. Shows more complex test scenarios.

  **WHY Each Reference Matters**:
  - `controller.py` — The executor must understand SimController's exact interface to write accurate mapping tables
  - `test_mode.py` — The executor must document TestMode's full command set accurately in Section 7
  - `platform.py` — The executor must reference the debug UART config and explain why we use UART3 VCP (115200, PB10/PB11) instead in Section 3
  - `test_basic.py` — The executor must show concrete examples of how tests will work unchanged in Section 6

  **Acceptance Criteria**:
  - [ ] File `docs/hil-architecture.md` exists
  - [ ] All 10 sections present (grep for ## headings)
  - [ ] Every section references at least 2 specific files with paths
  - [ ] Options comparison includes a table with pros/cons columns
  - [ ] Migration path has numbered phases with clear dependencies

  **QA Scenarios:**

  ```
  Scenario: Architecture document completeness
    Tool: Bash
    Preconditions: docs/hil-architecture.md written
    Steps:
      1. Run: grep -c '^## ' docs/hil-architecture.md
      2. Assert: count >= 10
      3. Run: grep -c 'test/integration/util/controller.py' docs/hil-architecture.md
      4. Assert: count >= 5 (referenced in multiple sections)
      5. Run: grep -c 'src/test_mode.py' docs/hil-architecture.md
      6. Assert: count >= 3
      7. Run: grep 'SimController\|HardwareController\|BaseController' docs/hil-architecture.md | wc -l
      8. Assert: count >= 10 (core concepts appear throughout)
    Expected Result: Document has all sections with rich codebase references
    Failure Indicators: Missing sections, no file references, generic content without repo specifics
    Evidence: .sisyphus/evidence/task-1-doc-completeness.txt

  Scenario: All referenced files actually exist
    Tool: Bash
    Preconditions: docs/hil-architecture.md written
    Steps:
      1. Extract all file paths mentioned in the document: grep -oP '[a-z]+/[a-z_/]+\.py' docs/hil-architecture.md | sort -u
      2. For each path, verify: test -f <path> && echo "OK: <path>" || echo "MISSING: <path>"
      3. Assert: zero MISSING lines
    Expected Result: Every file referenced in the document exists in the repo
    Failure Indicators: Any "MISSING" output
    Evidence: .sisyphus/evidence/task-1-file-references.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-doc-completeness.txt — Section count and reference counts
  - [ ] task-1-file-references.txt — File existence verification

  **Commit**: YES (group 1)
  - Message: `docs(hil): add hardware-in-the-loop testing architecture document`
  - Files: `docs/hil-architecture.md`
  - Pre-commit: QA scenarios pass

---

- [x] 2. BaseController ABC Extraction

  **What to do**:
  - Create `test/integration/util/base_controller.py` with abstract `BaseController` class
  - Extract the common interface from SimController: `start()`, `load()`, `shutdown()`, `query(data, commands=[])`
  - Define abstract methods using Python's `abc.ABC` and `@abstractmethod`
  - `start()` — Initialize the backend (launch simulator process OR connect to hardware)
  - `load()` — Perform initial setup (connect channels, unlock wallet, set up test state)
  - `shutdown()` — Clean up (kill process OR disconnect from hardware)
  - `query(data, commands=[])` — Send command data, execute GUI interactions, return response
  - Add type hints for all methods
  - Include docstrings explaining the contract each method must fulfill
  - Keep it minimal — no implementation logic, just the interface contract

  **Must NOT do**:
  - MUST NOT add unnecessary methods beyond what SimController actually uses
  - MUST NOT add configuration/settings management — keep it a pure interface
  - MUST NOT import anything beyond `abc` and standard library types

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small, well-defined file creation — extract 4 abstract methods into an ABC
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - None needed for a simple ABC

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 4, 5, 7, 8
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py` — SimController class: exact method signatures for `start()`, `load()`, `shutdown()`, `query(data, commands=[])`. The ABC must match these signatures exactly.
  - `src/hosts/core.py` — Abstract Host base class: shows the project's existing pattern for abstract base classes (init, update, enable, disable). Follow similar style.

  **WHY Each Reference Matters**:
  - `controller.py` — The executor MUST read this to extract the exact method signatures. The ABC must be a perfect superset of SimController's public interface.
  - `core.py` — Shows how the project already does abstract classes. Match the style (e.g., docstring conventions, import patterns).

  **Acceptance Criteria**:
  - [ ] File `test/integration/util/base_controller.py` exists
  - [ ] Class `BaseController` inherits from `abc.ABC`
  - [ ] Methods `start()`, `load()`, `shutdown()`, `query(data, commands=[])` are `@abstractmethod`
  - [ ] Type hints present on all methods
  - [ ] Importing `BaseController` works: `from util.base_controller import BaseController`

  **QA Scenarios:**

  ```
  Scenario: BaseController is a valid ABC with correct abstract methods
    Tool: Bash
    Preconditions: test/integration/util/base_controller.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.base_controller import BaseController
         import inspect
         assert inspect.isabstract(BaseController), 'Not abstract'
         expected = {'start', 'load', 'shutdown', 'query'}
         assert BaseController.__abstractmethods__ == expected, f'Wrong methods: {BaseController.__abstractmethods__}'
         sig = inspect.signature(BaseController.query)
         params = list(sig.parameters.keys())
         assert 'data' in params, f'Missing data param: {params}'
         assert 'commands' in params, f'Missing commands param: {params}'
         print('OK: BaseController ABC is correct')"
      2. Assert output contains: "OK: BaseController ABC is correct"
    Expected Result: BaseController is abstract with exactly 4 abstract methods matching SimController's interface
    Failure Indicators: ImportError, AssertionError, wrong method names
    Evidence: .sisyphus/evidence/task-2-abc-validation.txt

  Scenario: BaseController cannot be instantiated directly
    Tool: Bash
    Preconditions: test/integration/util/base_controller.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.base_controller import BaseController
         try:
           bc = BaseController()
           print('FAIL: Should not be instantiable')
         except TypeError as e:
           print(f'OK: Cannot instantiate: {e}')"
      2. Assert output starts with: "OK: Cannot instantiate"
    Expected Result: TypeError when trying to instantiate abstract class
    Failure Indicators: "FAIL" output, no TypeError
    Evidence: .sisyphus/evidence/task-2-abc-instantiation.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-abc-validation.txt
  - [ ] task-2-abc-instantiation.txt

  **Commit**: YES (group 2, with Task 8)
  - Message: `refactor(test): extract BaseController ABC from SimController`
  - Files: `test/integration/util/base_controller.py`
  - Pre-commit: QA scenarios pass

---

- [x] 3. STLinkManager — Hardware Lifecycle Control

  **What to do**:
  - Create `test/integration/util/stlink_manager.py` with `STLinkManager` class
  - Align with `SWDInterface` class from `docs/llm_testing_guide.md` (Section 6) but adapted for our TestMode integration
  - Implement lifecycle operations using `st-flash` (primary) and OpenOCD (for memory reads):
    - `flash(firmware_path, address='0x08000000')` — Flash firmware via `st-flash --reset write <path> <address>`
    - `reset()` — Hard reset via `st-flash reset`
    - `erase()` — Full flash erase via `st-flash erase` (for unbricking)
    - `halt()` — Halt CPU via OpenOCD (`init; halt; shutdown`)
    - `resume()` — Resume CPU via OpenOCD (`init; halt; resume; shutdown`)
    - `is_connected()` — Check ST-Link probe with `st-info --probe`
    - `read_memory(address, word_count=4)` — Read memory via OpenOCD (`mdw`) for marker system
  - Use `subprocess.run()` with `capture_output=True, text=True` pattern from guide's SWDInterface
  - Include configurable tool paths as constructor parameters with sensible defaults
  - Add timeout handling for flash operations (flash can take 30-60 seconds)
  - Add a `wait_for_boot(port, timeout=10)` method that waits for the device UART to become responsive after reset (sends `TEST_STATUS` and waits for `OK:` response)

  **Must NOT do**:
  - MUST NOT hard-code tool paths — make them constructor parameters with sensible defaults
  - MUST NOT implement UART communication — that's Task 5's job. `wait_for_boot()` should accept a serial port path and do minimal serial I/O only for boot detection.
  - MUST NOT require pyOCD as a dependency — use st-flash (primary) + OpenOCD (memory reads) via subprocess

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires understanding of OpenOCD CLI, STM32 flash process, and subprocess management with timeouts
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - None — straightforward Python subprocess work

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 7, 9
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py:SimController.start()` — Shows how simulator lifecycle is managed (subprocess.Popen). STLinkManager follows similar pattern but for hardware.
  - `test/integration/util/controller.py:SimController.shutdown()` — Shows process cleanup with os.killpg(). STLinkManager.reset() is the hardware equivalent.
  - `Makefile` — `make disco` target shows the STM32 build + flash commands. Extract the flash command pattern.

  **External References**:
  - `st-flash` commands: `st-flash write`, `st-flash reset`, `st-flash erase`, `st-info --probe`
  - OpenOCD for memory reads: `openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "init; halt; mdw <addr> <count>; shutdown"`
  - `docs/llm_testing_guide.md` Section 6 — `SWDInterface` class: Shows exact st-flash and OpenOCD command patterns to follow. **THIS IS THE PRIMARY REFERENCE for command syntax.**

  **WHY Each Reference Matters**:
  - `controller.py` — Shows the lifecycle management pattern the executor should follow (start/stop/cleanup)
  - `Makefile` — Contains actual flash commands used by this project, not generic STM32 commands

  **Acceptance Criteria**:
  - [ ] File `test/integration/util/stlink_manager.py` exists
  - [ ] Class `STLinkManager` with methods: `flash()`, `reset()`, `erase()`, `halt()`, `resume()`, `is_connected()`, `read_memory()`, `wait_for_boot()`
  - [ ] Importing works: `from util.stlink_manager import STLinkManager`
  - [ ] st-flash is the primary tool (not OpenOCD) for flash/reset operations
  - [ ] Timeout handling present for flash and wait_for_boot operations

  **QA Scenarios:**

  ```
  Scenario: STLinkManager has correct interface and is importable
    Tool: Bash
    Preconditions: test/integration/util/stlink_manager.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.stlink_manager import STLinkManager
         import inspect
         mgr = STLinkManager()
         methods = ['flash', 'reset', 'erase', 'halt', 'resume', 'is_connected', 'read_memory', 'wait_for_boot']
         for m in methods:
           assert hasattr(mgr, m), f'Missing method: {m}'
           assert callable(getattr(mgr, m)), f'Not callable: {m}'
         print('OK: STLinkManager has all required methods')"
      2. Assert output contains: "OK: STLinkManager has all required methods"
    Expected Result: All lifecycle methods present and callable
    Failure Indicators: ImportError, missing methods
    Evidence: .sisyphus/evidence/task-3-stlink-interface.txt

  Scenario: STLinkManager handles missing st-flash gracefully
    Tool: Bash
    Preconditions: test/integration/util/stlink_manager.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.stlink_manager import STLinkManager
         mgr = STLinkManager(stflash_path='/nonexistent/st-flash')
         try:
           mgr.reset()
           print('FAIL: Should have raised an error')
         except (FileNotFoundError, OSError, RuntimeError) as e:
           print(f'OK: Graceful error: {type(e).__name__}: {e}')"
      2. Assert output starts with: "OK: Graceful error"
    Expected Result: Clear error when OpenOCD not found, not a cryptic crash
    Failure Indicators: Unhandled exception, "FAIL" output
    Evidence: .sisyphus/evidence/task-3-stlink-missing-openocd.txt
  ```

  **Evidence to Capture:**
  - [ ] task-3-stlink-interface.txt
  - [ ] task-3-stlink-missing-openocd.txt

  **Commit**: YES (group 3)
  - Message: `feat(test): add STLinkManager for hardware lifecycle control`
  - Files: `test/integration/util/stlink_manager.py`
  - Pre-commit: QA scenarios pass


- [x] 4. TestMode UART Extension (Firmware Side)

  **What to do**:
  - Modify `src/test_mode.py` to also listen on UART3 VCP alongside stdin
  - In `TestMode.__init__()`, detect if running on hardware (`not platform.simulator`) and if so, open UART3 VCP: `self.uart = pyb.UART(3, 115200)` on pins PB10 (TX) / PB11 (RX). This is the ST-Link Virtual COM Port, NOT the debug UART in platform.py.
  - In the polling loop (`update()` method), add UART polling alongside stdin polling:
    ```python
    if not platform.simulator and self.uart and self.uart.any():
        line = self.uart.readline()
        if line:
            await self._process_command(line.decode().strip())
    ```
  - Extract command processing from the existing stdin handler into a shared `_process_command(cmd_str)` method
  - For UART responses, write to `self.uart.write(response + '\n')` instead of `print()` when the command came from UART
  - Add a `_respond(response, source='stdin')` method that routes output to the correct channel:
    - `source='stdin'` → `print(response)` (existing behavior)
    - `source='uart'` → `self.uart.write((response + '\n').encode())`
  - Ensure the command processing is identical regardless of source channel — same command set, same responses
  - The existing stdin path must remain unchanged for simulator compatibility

  **Must NOT do**:
  - MUST NOT use pyb.UART("YB", 9600) from platform.py — that is the debug UART, NOT the VCP. Use `pyb.UART(3, 115200)` for UART3 VCP.
  - MUST NOT break existing stdin-based TestMode operation (simulator must still work)
  - MUST NOT add new commands — only add the UART transport, not new functionality
  - MUST NOT import new external modules — use only `pyb.UART` and `platform.simulator` which are already available

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Modifying existing firmware code requires understanding asyncio patterns, MicroPython UART API, and the full TestMode command flow to avoid breaking existing functionality
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - None needed — MicroPython-specific, no external frameworks

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5, 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7
  - **Blocked By**: Tasks 1 (architecture decisions), 2 (base interface)

  **References**:

  **Pattern References**:
  - `src/test_mode.py` — **FULL FILE** — The executor must understand the entire TestMode class before modifying. Key areas: `__init__()` (line ~20-40), `update()` polling loop (line ~50-80), command dispatch (line ~100+), response sending. Read carefully before making any changes.
  - `src/platform.py:316` — `stlk = pyb.UART("YB", 9600)` — This is the DEBUG UART, NOT what we use. Shown for reference to understand the distinction. Our UART3 VCP uses `pyb.UART(3, 115200)` on PB10/PB11.
  - `src/platform.py` — `simulator` boolean — Use this to guard UART code: `if not platform.simulator:`
  - `docs/llm_testing_guide.md` — Existing HIL guide showing VCPReader pattern using UART3 VCP at 115200 baud. Follow this pattern for firmware-side UART init.

  **API/Type References**:
  - MicroPython `pyb.UART` API: `uart.any()` returns bytes available, `uart.readline()` reads a line, `uart.write(bytes)` sends data
  - MicroPython `uselect.poll()` — Used by existing stdin polling. UART can be added to the same poll object OR checked separately.

  **Test References**:
  - `src/test_mode.py` existing stdin handling — The executor must maintain identical behavior for stdin while adding UART as a second channel

  **WHY Each Reference Matters**:
  - `test_mode.py` — This is the file being modified. The executor must read it entirely to understand where to insert UART polling without disrupting the asyncio flow.
  - `platform.py` — Provides the `simulator` boolean flag to guard UART code. The debug UART at line 316 is NOT used — we create our own UART3 instance.

  **Acceptance Criteria**:
  - [ ] `src/test_mode.py` modified with UART polling code
  - [ ] Existing stdin-based commands still work (simulator compatibility)
  - [ ] UART responses go to UART, stdin responses go to stdout
  - [ ] No new imports beyond what's already in the file + `platform`
  - [ ] Builds successfully: `make unix` (simulator build as smoke test)

  **QA Scenarios:**

  ```
  Scenario: TestMode UART code is present and syntactically correct
    Tool: Bash
    Preconditions: src/test_mode.py modified
    Steps:
      1. Run: grep -n 'uart' src/test_mode.py
      2. Assert: at least 3 lines reference uart (init, read, write)
      3. Run: grep -n 'platform.simulator\|UART(3\|115200' src/test_mode.py
      4. Assert: at least 1 line guards UART code with simulator check
      5. Run: python3 -c "import ast; ast.parse(open('src/test_mode.py').read()); print('OK: Syntax valid')"
      6. Assert output: "OK: Syntax valid"
    Expected Result: UART code present, properly guarded, syntactically valid Python
    Failure Indicators: No uart references, missing simulator guard, syntax error
    Evidence: .sisyphus/evidence/task-4-uart-code-check.txt

  Scenario: Existing TestMode stdin path is preserved
    Tool: Bash
    Preconditions: src/test_mode.py modified
    Steps:
      1. Run: grep -n 'stdin\|sys.stdin\|uselect\|poll' src/test_mode.py
      2. Assert: stdin polling code still present (at least 2 matches)
      3. Run: grep -n 'print(' src/test_mode.py | grep -v '#'
      4. Assert: print-based responses still present for stdin path
    Expected Result: Stdin handling completely preserved alongside new UART handling
    Failure Indicators: Stdin references removed or modified
    Evidence: .sisyphus/evidence/task-4-stdin-preserved.txt

  Scenario: Simulator build succeeds
    Tool: Bash
    Preconditions: src/test_mode.py modified
    Steps:
      1. Run: make unix 2>&1 | tail -20
      2. Assert: build completes without error (exit code 0)
    Expected Result: Modified test_mode.py doesn't break the simulator build
    Failure Indicators: Compilation error, import error
    Evidence: .sisyphus/evidence/task-4-build-check.txt
  ```

  **Evidence to Capture:**
  - [ ] task-4-uart-code-check.txt
  - [ ] task-4-stdin-preserved.txt
  - [ ] task-4-build-check.txt

  **Commit**: YES (group 4)
  - Message: `feat(firmware): extend TestMode to listen on UART3 VCP at 115200`
  - Files: `src/test_mode.py`
  - Pre-commit: `make unix` succeeds, QA scenarios pass

---

- [x] 5. UARTChannel — Host-Side Serial Communication

  **What to do**:
  - Create `test/integration/util/uart_channel.py` with `UARTChannel` class
  - This is the host-side equivalent of `TCPSocket` from controller.py, but over serial/UART
  - Constructor: `UARTChannel(port='/dev/ttyACM0', baudrate=115200, timeout=5)` using `pyserial` — follows VCPReader pattern from docs/llm_testing_guide.md
  - Methods (mirroring TCPSocket's interface):
    - `open()` — Open serial port connection
    - `close()` — Close serial port
    - `send(data)` — Send command string over UART (append `\n`)
    - `readline(timeout=None)` — Read one line response (up to `\n`), with timeout
    - `query(command, timeout=5)` — Send command + read response (convenience wrapper)
    - `drain()` — Read and discard any buffered data (for synchronization after reset)
  - Handle serial port errors gracefully (port not found, permission denied, timeout)
  - Include a `wait_for_ready(timeout=30)` method that polls with `TEST_STATUS` until device responds with `OK:`
  - Line protocol: send `COMMAND\n`, receive `OK:data\n` or `ERROR:message\n`

  **Must NOT do**:
  - MUST NOT implement command mapping logic — that's Task 6's job. UARTChannel sends raw strings.
  - MUST NOT hard-code port paths — always accept as constructor parameter
  - MUST NOT add retry logic beyond simple timeout — keep it simple

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires pyserial knowledge, serial port error handling, and timeout management
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4, 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7
  - **Blocked By**: Task 2 (base interface pattern)

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py:TCPSocket` — **THIS IS THE PATTERN TO MIRROR**. TCPSocket has `readline()`, `send()`, `query()`. UARTChannel must provide the same interface but over serial instead of TCP. Read TCPSocket's implementation and replicate the structure.

  **External References**:
  - pyserial: `serial.Serial(port, baudrate, timeout)`, `.readline()`, `.write()`, `.reset_input_buffer()`
  - `docs/llm_testing_guide.md:VCPReader` — Existing VCPReader class using `serial.Serial(port, 115200, timeout=1)` with `read_line()`, `wait_for()`, `wait_for_marker()`, `clear_buffer()`. Our UARTChannel should follow similar patterns, particularly the timeout handling and buffer clearing approach.

  **WHY Each Reference Matters**:
  - `TCPSocket` — The executor must match this interface so HardwareController can swap TCPSocket for UARTChannel transparently

  **Acceptance Criteria**:
  - [ ] File `test/integration/util/uart_channel.py` exists
  - [ ] Class `UARTChannel` with methods: `open()`, `close()`, `send()`, `readline()`, `query()`, `drain()`, `wait_for_ready()`
  - [ ] Importing works: `from util.uart_channel import UARTChannel`
  - [ ] pyserial is the only external dependency
  - [ ] Timeout handling on all read operations

  **QA Scenarios:**

  ```
  Scenario: UARTChannel has correct interface
    Tool: Bash
    Preconditions: test/integration/util/uart_channel.py written, pyserial installed
    Steps:
      1. cd test/integration && python3 -c "
         from util.uart_channel import UARTChannel
         import inspect
         methods = ['open', 'close', 'send', 'readline', 'query', 'drain', 'wait_for_ready']
         for m in methods:
           assert hasattr(UARTChannel, m), f'Missing method: {m}'
         sig = inspect.signature(UARTChannel.__init__)
         params = list(sig.parameters.keys())
         assert 'port' in params, f'Missing port param: {params}'
         assert 'baudrate' in params, f'Missing baudrate param: {params}'
         print('OK: UARTChannel interface correct')"
      2. Assert output: "OK: UARTChannel interface correct"
    Expected Result: All serial communication methods present with correct constructor signature
    Failure Indicators: ImportError, missing methods, wrong constructor params
    Evidence: .sisyphus/evidence/task-5-uart-interface.txt

  Scenario: UARTChannel handles missing port gracefully
    Tool: Bash
    Preconditions: test/integration/util/uart_channel.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.uart_channel import UARTChannel
         ch = UARTChannel(port='/dev/nonexistent_port_xyz')
         try:
           ch.open()
           print('FAIL: Should have raised error')
         except (serial.SerialException, OSError, FileNotFoundError) as e:
           print(f'OK: Graceful error: {type(e).__name__}')"
      2. Assert output starts with: "OK: Graceful error"
    Expected Result: Clear error when port doesn't exist
    Failure Indicators: "FAIL" output, unhandled crash
    Evidence: .sisyphus/evidence/task-5-uart-missing-port.txt
  ```

  **Evidence to Capture:**
  - [ ] task-5-uart-interface.txt
  - [ ] task-5-uart-missing-port.txt

  **Commit**: YES (group 5, with Task 6)
  - Message: `feat(test): add UARTChannel and command protocol mapping`
  - Files: `test/integration/util/uart_channel.py`
  - Pre-commit: QA scenarios pass

---

- [x] 6. Command Protocol Mapping (SimController Commands → TestMode Commands)

  **What to do**:
  - Create `test/integration/util/protocol.py` with command mapping logic
  - This module translates SimController's dual-channel protocol (USB commands + GUI commands) into TestMode's single-channel protocol (TEST_* commands over UART)
  - Core mapping class: `CommandMapper` with methods:
    - `map_usb_command(data: bytes) -> str` — Convert USB binary command to TEST_* string command
    - `map_gui_command(command) -> str` — Convert GUI JSON command to TEST_UI_* string command
    - `parse_response(response: str) -> bytes` — Parse `OK:data` / `ERROR:message` into the format tests expect
  - Specific mappings (derived from analyzing test_basic.py and test_mode.py):
    - USB `addwallet` command → requires sequence: `TEST_UI_SET:` for wallet data
    - USB `sign` command + GUI `True` → `TEST_SIGN:<hex>` (TestMode handles confirmation internally)
    - USB `xpub` query → `TEST_XPUB:<path>`
    - GUI PIN entry → `TEST_UI_PIN:<digits>`
    - GUI confirmation (True/False) → `TEST_UI_SET:confirm` / `TEST_UI_SET:cancel`
    - GUI screen value setting → `TEST_UI_SET:<value>`
  - Include a mapping table as a module-level constant or config
  - Handle unmapped commands with a clear error message
  - Consider including memory marker protocol (`stm.mem32[]` addresses) as optional diagnostic enrichment — see MarkerReader in docs/llm_testing_guide.md. This can help CommandMapper optionally report boot-stage markers read via OpenOCD for debugging failures.

  **Must NOT do**:
  - MUST NOT implement serial communication — that's UARTChannel's job
  - MUST NOT modify existing test commands or TestMode commands
  - MUST NOT add commands that don't exist in TestMode

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires careful analysis of both SimController's command protocol and TestMode's command set to create accurate mappings
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4, 5)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7
  - **Blocked By**: Task 1 (architecture doc defines the mapping)

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py:SimController.query()` — Shows the USB command + GUI command protocol. The mapper must handle both command types.
  - `test/integration/tests/test_basic.py` — Shows ALL the actual command patterns used by tests: what data is sent, what GUI commands follow. This is the definitive list of what needs mapping.
  - `src/test_mode.py` — Shows ALL available TEST_* commands. The mapper can ONLY use commands that exist here.
  - `src/hosts/usb.py:USBHost` — Shows how USB commands are processed on the firmware side. Helps understand what the USB binary protocol means.
  - `src/gui/tcp_gui.py:TCPGUI` — Shows how GUI commands are processed. Helps understand what JSON values map to which screen actions.

  **WHY Each Reference Matters**:
  - `test_basic.py` — THE SOURCE OF TRUTH for what commands tests actually send. Every sim.query() call = one mapping needed.
  - `test_mode.py` — THE SOURCE OF TRUTH for what commands the device accepts. The mapper cannot invent commands.
  - `usb.py` and `tcp_gui.py` — Help understand the semantics of USB and GUI commands to create correct mappings.

  **Acceptance Criteria**:
  - [ ] File `test/integration/util/protocol.py` exists
  - [ ] Class `CommandMapper` with `map_usb_command()`, `map_gui_command()`, `parse_response()`
  - [ ] Mapping covers all commands used in test_basic.py
  - [ ] Unmapped commands raise clear errors
  - [ ] Importing works: `from util.protocol import CommandMapper`

  **QA Scenarios:**

  ```
  Scenario: CommandMapper handles known command types
    Tool: Bash
    Preconditions: test/integration/util/protocol.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.protocol import CommandMapper
         mapper = CommandMapper()
         # Test GUI command mapping
         result = mapper.map_gui_command(True)
         assert 'TEST_UI' in result, f'GUI True should map to TEST_UI: {result}'
         result = mapper.map_gui_command(False)
         assert 'TEST_UI' in result, f'GUI False should map to TEST_UI: {result}'
         print('OK: Known command mappings work')"
      2. Assert output: "OK: Known command mappings work"
    Expected Result: GUI True/False correctly map to TEST_UI_SET commands
    Failure Indicators: Wrong mapping, KeyError, ImportError
    Evidence: .sisyphus/evidence/task-6-command-mapping.txt

  Scenario: CommandMapper rejects unknown commands gracefully
    Tool: Bash
    Preconditions: test/integration/util/protocol.py written
    Steps:
      1. cd test/integration && python3 -c "
         from util.protocol import CommandMapper
         mapper = CommandMapper()
         try:
           mapper.map_gui_command('UNKNOWN_NONSENSE_CMD')
           print('WARNING: No error for unknown command (may be OK if passthrough)')  
         except (ValueError, KeyError) as e:
           print(f'OK: Unknown command rejected: {e}')"
      2. Assert output starts with: "OK:" or "WARNING:"
    Expected Result: Unknown commands either error or pass through with warning
    Failure Indicators: Unhandled exception, silent wrong mapping
    Evidence: .sisyphus/evidence/task-6-unknown-command.txt
  ```

  **Evidence to Capture:**
  - [ ] task-6-command-mapping.txt
  - [ ] task-6-unknown-command.txt

  **Commit**: YES (group 5, with Task 5)
  - Message: `feat(test): add UARTChannel and command protocol mapping`
  - Files: `test/integration/util/protocol.py`
  - Pre-commit: QA scenarios pass


- [ ] 7. HardwareController Assembly

  **What to do**:
  - Create `test/integration/util/hardware_controller.py` with `HardwareController` class extending `BaseController`
  - This is the main integration piece: combines `STLinkManager` (lifecycle), `UARTChannel` (communication), and `CommandMapper` (protocol translation)
  - Constructor: `HardwareController(port='/dev/ttyACM0', baudrate=115200, stflash_path='st-flash')` — follows HardwareTestRig composition pattern from docs/llm_testing_guide.md
  - Implement the `BaseController` interface:
    - `start()` — Verify ST-Link connection via `STLinkManager.is_connected()`. Optionally flash firmware if a firmware path is provided. Reset the device. Wait for boot via `UARTChannel.wait_for_ready()`.
    - `load()` — Open UART channel. Drain any buffered data. Send `TEST_STATUS` to verify device is responsive. Send `TEST_PIN:<pin>` to unlock. Send `TEST_SET_NETWORK:regtest` for test setup (matching SimController.load() which sets up the wallet for testing).
    - `shutdown()` — Close UART channel. Optionally halt device via STLinkManager.
    - `query(data, commands=[])` — The critical method:
      1. Map `data` bytes to TEST_* command via `CommandMapper.map_usb_command(data)`
      2. Send command via `UARTChannel.send()`
      3. Read response via `UARTChannel.readline()`
      4. For each item in `commands[]`, map via `CommandMapper.map_gui_command()` and send via UART
      5. If commands were sent, read final response
      6. Parse response via `CommandMapper.parse_response()` to match format tests expect
      7. Return response bytes matching SimController's return format
  - Add `reset(hard=False)` convenience method: soft reset via `TEST_RESET` UART command by default, hard reset via `STLinkManager.reset()` when `hard=True`
  - Add timeout handling: if device doesn't respond within N seconds, attempt soft reset + retry once, then raise error
  - Create module-level singleton: `hw = HardwareController()` (similar to `sim = SimController()` in controller.py)

  **Must NOT do**:
  - MUST NOT duplicate logic from STLinkManager, UARTChannel, or CommandMapper — compose them
  - MUST NOT modify the `query()` return format — tests expect the same bytes format as SimController returns
  - MUST NOT add test-specific logic (like specific test setup sequences) — keep it generic
  - MUST NOT add auto-flash on every start — flash should be opt-in

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Integration of 3 components with careful protocol orchestration. Must match SimController's exact behavior for test compatibility.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential within wave, but Wave 3 tasks can be parallelized)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Tasks 2 (BaseController), 4 (TestMode UART), 5 (UARTChannel), 6 (CommandMapper)

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py:SimController` — **THE PRIMARY REFERENCE**. HardwareController must implement the same interface with the same return value formats. Pay special attention to `query()` — the exact sequence of send/receive/gui-interact/receive must be replicated.
  - `test/integration/util/base_controller.py:BaseController` — The ABC to extend (created in Task 2)
  - `test/integration/util/stlink_manager.py:STLinkManager` — Lifecycle component (created in Task 3)
  - `test/integration/util/uart_channel.py:UARTChannel` — Communication component (created in Task 5)
  - `test/integration/util/protocol.py:CommandMapper` — Protocol translation (created in Task 6)

  - `docs/llm_testing_guide.md:HardwareTestRig` — Existing composition pattern combining VCPReader + SWDInterface + MarkerReader. Our HardwareController follows the same composition approach. Reference for optional marker reading on failure for diagnostic enrichment.
  - `docs/llm_testing_guide.md:MarkerReader` — Memory marker system using `stm.mem32[]` addresses read via OpenOCD. Consider incorporating as optional diagnostic channel — on test failure, read marker addresses to determine which boot stage the device reached.
  **Test References**:
  - `test/integration/tests/test_basic.py` — Shows exactly what tests send to `query()` and what they expect back. HardwareController must produce identical return values.

  **WHY Each Reference Matters**:
  - `SimController` — The GOLDEN REFERENCE. HardwareController is a drop-in replacement. Same interface, same behavior, different transport.
  - `test_basic.py` — The executor must verify that HardwareController's `query()` returns would satisfy every assertion in the tests.

  **Acceptance Criteria**:
  - [ ] File `test/integration/util/hardware_controller.py` exists
  - [ ] `HardwareController` extends `BaseController`
  - [ ] Implements all abstract methods: `start()`, `load()`, `shutdown()`, `query(data, commands=[])`
  - [ ] Composes STLinkManager, UARTChannel, CommandMapper
  - [ ] Module-level `hw = HardwareController()` singleton exists (or factory)
  - [ ] Import works: `from util.hardware_controller import HardwareController`

  **QA Scenarios:**

  ```
  Scenario: HardwareController is a valid BaseController implementation
    Tool: Bash
    Preconditions: All Wave 1-2 artifacts created
    Steps:
      1. cd test/integration && python3 -c "
         from util.hardware_controller import HardwareController
         from util.base_controller import BaseController
         assert issubclass(HardwareController, BaseController), 'Not a BaseController subclass'
         # Verify it's instantiable (not abstract)
         hc = HardwareController(port='/dev/null')
         assert hasattr(hc, 'start'), 'Missing start'
         assert hasattr(hc, 'load'), 'Missing load'
         assert hasattr(hc, 'shutdown'), 'Missing shutdown'
         assert hasattr(hc, 'query'), 'Missing query'
         assert hasattr(hc, 'reset'), 'Missing reset convenience method'
         print('OK: HardwareController implements BaseController')"
      2. Assert output: "OK: HardwareController implements BaseController"
    Expected Result: HardwareController is a concrete subclass of BaseController with all methods
    Failure Indicators: ImportError, missing methods, still abstract
    Evidence: .sisyphus/evidence/task-7-hw-controller-interface.txt

  Scenario: HardwareController composes the right components
    Tool: Bash
    Preconditions: All Wave 1-2 artifacts created
    Steps:
      1. cd test/integration && python3 -c "
         import ast
         tree = ast.parse(open('util/hardware_controller.py').read())
         source = open('util/hardware_controller.py').read()
         assert 'STLinkManager' in source, 'Missing STLinkManager usage'
         assert 'UARTChannel' in source, 'Missing UARTChannel usage'
         assert 'CommandMapper' in source, 'Missing CommandMapper usage'
         print('OK: Composes all required components')"
      2. Assert output: "OK: Composes all required components"
    Expected Result: HardwareController uses all three Wave 1-2 components
    Failure Indicators: Missing component references
    Evidence: .sisyphus/evidence/task-7-hw-controller-composition.txt

  Scenario: query() method signature matches SimController
    Tool: Bash
    Preconditions: hardware_controller.py exists
    Steps:
      1. cd test/integration && python3 -c "
         import inspect
         from util.hardware_controller import HardwareController
         from util.controller import SimController
         hw_sig = inspect.signature(HardwareController.query)
         sim_sig = inspect.signature(SimController.query)
         hw_params = set(hw_sig.parameters.keys())
         sim_params = set(sim_sig.parameters.keys())
         assert hw_params == sim_params, f'Param mismatch: HW={hw_params} SIM={sim_params}'
         print('OK: query() signatures match')"
      2. Assert output: "OK: query() signatures match"
    Expected Result: Identical method signatures
    Failure Indicators: Parameter name mismatch
    Evidence: .sisyphus/evidence/task-7-hw-controller-signature.txt
  ```

  **Evidence to Capture:**
  - [ ] task-7-hw-controller-interface.txt
  - [ ] task-7-hw-controller-composition.txt
  - [ ] task-7-hw-controller-signature.txt

  **Commit**: YES (group 6)
  - Message: `feat(test): implement HardwareController for HIL testing`
  - Files: `test/integration/util/hardware_controller.py`
  - Pre-commit: QA scenarios pass

---

- [x] 8. SimController Refactor to Extend BaseController

  **What to do**:
  - Modify `test/integration/util/controller.py` to make `SimController` extend `BaseController`
  - Add `from util.base_controller import BaseController` import
  - Change class declaration: `class SimController(BaseController):`
  - Verify all existing methods already satisfy the ABC contract (they should — BaseController was extracted from SimController)
  - Ensure `from util.controller import sim` still works (existing test import path)
  - Run existing tests to confirm zero regression

  **Must NOT do**:
  - MUST NOT change SimController's behavior — only add the base class
  - MUST NOT change method signatures
  - MUST NOT change the global `sim = SimController()` singleton
  - MUST NOT modify test files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Minimal change — add one import and change one class declaration line
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 9)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 10
  - **Blocked By**: Task 2 (BaseController ABC)

  **References**:

  **Pattern References**:
  - `test/integration/util/controller.py` — The file to modify. SimController class definition.
  - `test/integration/util/base_controller.py` — The ABC to extend (created in Task 2)

  **Acceptance Criteria**:
  - [ ] `SimController` extends `BaseController`
  - [ ] `from util.controller import sim` still works
  - [ ] `isinstance(sim, BaseController)` returns True
  - [ ] Existing simulator tests pass unchanged

  **QA Scenarios:**

  ```
  Scenario: SimController extends BaseController correctly
    Tool: Bash
    Preconditions: controller.py modified, base_controller.py exists
    Steps:
      1. cd test/integration && python3 -c "
         from util.controller import SimController, sim
         from util.base_controller import BaseController
         assert issubclass(SimController, BaseController), 'SimController should extend BaseController'
         assert isinstance(sim, BaseController), 'sim singleton should be a BaseController'
         print('OK: SimController extends BaseController')"
      2. Assert output: "OK: SimController extends BaseController"
    Expected Result: SimController is now a BaseController subclass
    Failure Indicators: Not a subclass, import error
    Evidence: .sisyphus/evidence/task-8-sim-extends-base.txt

  Scenario: Existing tests still pass (no regression)
    Tool: Bash
    Preconditions: controller.py modified
    Steps:
      1. Run: cd test/integration && python3 run_tests.py 2>&1 | tail -5
      2. Assert: output contains "OK" or "passed" and exit code 0
    Expected Result: All existing simulator tests pass unchanged
    Failure Indicators: Any test failure, import error
    Evidence: .sisyphus/evidence/task-8-regression-test.txt
  ```

  **Evidence to Capture:**
  - [ ] task-8-sim-extends-base.txt
  - [ ] task-8-regression-test.txt

  **Commit**: YES (group 2, with Task 2)
  - Message: `refactor(test): extract BaseController ABC from SimController`
  - Files: `test/integration/util/controller.py`
  - Pre-commit: existing tests pass

---

- [ ] 9. Test Runner --hardware Flag + Makefile Targets

  **What to do**:
  - Modify `test/integration/run_tests.py` to support `--hardware` and `--port` flags:
    - `--hardware` — Use HardwareController instead of SimController
    - `--port /dev/ttyACM0` — Serial port for UART3 VCP (required with --hardware)
    - `--flash path/to/firmware.bin` — Optional: flash firmware before testing
    - `--hard-reset` — Use ST-Link hard reset between tests instead of software reset
  - When `--hardware` is specified:
    - Import `HardwareController` instead of `SimController`
    - Set the module-level controller variable that tests import
    - The key mechanism: tests do `from util.controller import sim`. The runner must make `sim` point to either a SimController or HardwareController instance.
    - Approach: In run_tests.py, after parsing args, if `--hardware`: create HardwareController, then monkey-patch `util.controller.sim = hw_instance`. Tests import `sim` at module load time, so ensure the patch happens before test module imports.
  - Modify `Makefile` to add:
    - `test-hil` target: `cd test/integration && python3 run_tests.py --hardware --port $(PORT)`
    - `PORT` variable defaulting to `/dev/ttyACM0`
    - `test-hil-flash` target: `make test-hil FLASH=path/to/firmware.bin`

  **Must NOT do**:
  - MUST NOT modify test files (test_basic.py, test_with_rpc.py)
  - MUST NOT change the default behavior of `run_tests.py` (without flags, it should work exactly as before)
  - MUST NOT make --hardware the default

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Adding argparse flags and Makefile targets is straightforward
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 8)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 3 (STLinkManager for flash support), 7 (HardwareController)

  **References**:

  **Pattern References**:
  - `test/integration/run_tests.py` — The file to modify. Current test runner with no argument parsing.
  - `test/integration/util/controller.py` — Shows how `sim` singleton is created and exported. The runner must patch this.
  - `Makefile` — Existing targets: `test`, `disco`, `unix`. New targets follow same conventions.

  **WHY Each Reference Matters**:
  - `run_tests.py` — Executor must understand current test discovery and execution to add flags without breaking it
  - `controller.py` — Executor must understand how `sim` is imported by tests to implement the monkey-patch correctly

  **Acceptance Criteria**:
  - [ ] `python3 run_tests.py --help` shows --hardware, --port, --flash, --hard-reset flags
  - [ ] `python3 run_tests.py` (no flags) still runs simulator tests as before
  - [ ] `make -n test-hil` shows the hardware test recipe
  - [ ] `make -n test-hil PORT=/dev/ttyUSB0` uses the specified port

  **QA Scenarios:**

  ```
  Scenario: Test runner help shows new flags
    Tool: Bash
    Preconditions: run_tests.py modified
    Steps:
      1. cd test/integration && python3 run_tests.py --help 2>&1
      2. Assert output contains: "--hardware"
      3. Assert output contains: "--port"
    Expected Result: New flags visible in help output
    Failure Indicators: Missing flags, argparse error
    Evidence: .sisyphus/evidence/task-9-runner-help.txt

  Scenario: Default mode unchanged (no regression)
    Tool: Bash
    Preconditions: run_tests.py modified
    Steps:
      1. cd test/integration && python3 run_tests.py 2>&1 | tail -5
      2. Assert: tests run normally (same as before modification)
    Expected Result: Without --hardware flag, behavior is identical to original
    Failure Indicators: Different behavior, import error
    Evidence: .sisyphus/evidence/task-9-default-mode.txt

  Scenario: Makefile has test-hil target
    Tool: Bash
    Preconditions: Makefile modified
    Steps:
      1. Run: make -n test-hil PORT=/dev/ttyUSB0 2>&1
      2. Assert output contains: "run_tests.py" and "--hardware"
    Expected Result: Makefile target properly invokes test runner with hardware flag
    Failure Indicators: "No rule to make target", wrong command
    Evidence: .sisyphus/evidence/task-9-makefile-target.txt
  ```

  **Evidence to Capture:**
  - [ ] task-9-runner-help.txt
  - [ ] task-9-default-mode.txt
  - [ ] task-9-makefile-target.txt

  **Commit**: YES (group 7)
  - Message: `feat(test): add --hardware flag to test runner and Makefile targets`
  - Files: `test/integration/run_tests.py`, `Makefile`
  - Pre-commit: QA scenarios pass


- [ ] 10. Integration Test — Run Existing Tests Through Refactored SimController

  **What to do**:
  - This is the critical smoke test: run the existing test suite through the refactored SimController (which now extends BaseController) to verify zero regression
  - Steps:
    1. Build the simulator: `make unix`
    2. Run the full test suite: `cd test/integration && python3 run_tests.py`
    3. Verify ALL tests pass with no modifications
    4. Verify that `sim` is now an instance of `BaseController`: add a quick assertion in run_tests.py or run inline
    5. Verify that importing HardwareController doesn't crash (even if we can't test against real hardware): `python3 -c "from util.hardware_controller import HardwareController"`
    6. Test the `--hardware` flag parsing (it will fail to connect, but should parse correctly): `python3 run_tests.py --hardware --port /dev/null 2>&1` should show a connection error, not an argparse error
  - This task produces no new code — it's pure verification of Tasks 2-9

  **Must NOT do**:
  - MUST NOT modify any files — this is a read-only verification task
  - MUST NOT skip any test — run the complete suite

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Must build simulator and run full test suite, analyzing results carefully
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 11)
  - **Parallel Group**: Wave 4
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 7, 8, 9 (all Wave 3 outputs needed)

  **References**:

  **Pattern References**:
  - `test/integration/run_tests.py` — The test runner to execute
  - `Makefile` — `make unix` and `make test` targets

  **Acceptance Criteria**:
  - [ ] `make unix` builds successfully
  - [ ] `python3 run_tests.py` passes ALL existing tests (zero failures)
  - [ ] `from util.hardware_controller import HardwareController` doesn't crash
  - [ ] `python3 run_tests.py --hardware --port /dev/null` shows connection error (not argparse error)

  **QA Scenarios:**

  ```
  Scenario: Full simulator test suite passes after refactoring
    Tool: Bash
    Preconditions: All Tasks 1-9 completed
    Steps:
      1. Run: make unix 2>&1 | tail -5
      2. Assert: build succeeds (exit code 0)
      3. Run: cd test/integration && python3 run_tests.py 2>&1
      4. Assert: output contains test results with 0 failures
      5. Assert: exit code 0
    Expected Result: All existing tests pass unchanged through refactored SimController
    Failure Indicators: Any test failure, build error, import error
    Evidence: .sisyphus/evidence/task-10-full-test-suite.txt

  Scenario: HardwareController is importable and --hardware flag works
    Tool: Bash
    Preconditions: All Tasks 1-9 completed
    Steps:
      1. cd test/integration && python3 -c "
         from util.hardware_controller import HardwareController
         from util.base_controller import BaseController
         assert issubclass(HardwareController, BaseController)
         print('OK: HardwareController importable')"
      2. Assert output: "OK: HardwareController importable"
      3. Run: cd test/integration && python3 run_tests.py --hardware --port /dev/null 2>&1; echo "EXIT:$?"
      4. Assert: output does NOT contain "unrecognized arguments" (argparse would say this)
      5. Assert: output contains connection/port error (expected — /dev/null is not a real device)
    Expected Result: Hardware path code loads correctly, fails at connection (expected), not at parsing
    Failure Indicators: Argparse error, ImportError, unexpected crash
    Evidence: .sisyphus/evidence/task-10-hardware-import.txt
  ```

  **Evidence to Capture:**
  - [ ] task-10-full-test-suite.txt
  - [ ] task-10-hardware-import.txt

  **Commit**: YES (group 8, with Task 11)
  - Message: `test(hil): verify refactored controller with existing test suite`
  - Files: none (verification only, evidence files)
  - Pre-commit: All QA scenarios pass

---

- [ ] 11. Documentation Review + Cross-Reference Verification

  **What to do**:
  - Review `docs/hil-architecture.md` (created in Task 1) against the actual implementation (Tasks 2-9)
  - Verify:
    1. All file paths mentioned in the document actually exist now (some were proposed, now they should be real)
    2. Class names and method signatures in the document match the actual code
    3. The migration path in the document matches what was actually built
    4. The architecture diagram/description matches the actual component relationships
  - Update the architecture document with any corrections:
    - Fix any file paths that changed during implementation
    - Add actual line numbers for key code sections
    - Update the "concrete next files" section to reflect what was actually created
  - Add a "Current Status" section at the bottom documenting what's been implemented vs what remains (e.g., real hardware testing not yet validated)

  **Must NOT do**:
  - MUST NOT rewrite the architecture document — only correct factual inaccuracies
  - MUST NOT add new sections beyond corrections and status update

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Cross-reference checking and minor document corrections
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 10)
  - **Parallel Group**: Wave 4
  - **Blocks**: F1-F4
  - **Blocked By**: Task 1 (architecture doc), Tasks 2-9 (implementation to verify against)

  **References**:

  **Pattern References**:
  - `docs/hil-architecture.md` — The document to verify and update
  - All `test/integration/util/*.py` files — The implementations to verify against
  - `src/test_mode.py` — The modified firmware file to verify against

  **Acceptance Criteria**:
  - [ ] All file paths in docs/hil-architecture.md exist in the repo
  - [ ] Class/method names in document match actual code
  - [ ] "Current Status" section added to document
  - [ ] No broken references in the document

  **QA Scenarios:**

  ```
  Scenario: All file references in architecture doc are valid
    Tool: Bash
    Preconditions: docs/hil-architecture.md updated
    Steps:
      1. Extract file paths: grep -oP '[a-z]+/[a-z_/]+\.py' docs/hil-architecture.md | sort -u
      2. For each path: test -f <path> && echo "OK: <path>" || echo "MISSING: <path>"
      3. Assert: zero MISSING lines
    Expected Result: Every referenced file exists
    Failure Indicators: Any MISSING output
    Evidence: .sisyphus/evidence/task-11-doc-references.txt

  Scenario: Architecture doc has current status section
    Tool: Bash
    Preconditions: docs/hil-architecture.md updated
    Steps:
      1. Run: grep -i 'current status\|implementation status' docs/hil-architecture.md
      2. Assert: at least 1 match
    Expected Result: Status section present documenting what's implemented
    Failure Indicators: No status section found
    Evidence: .sisyphus/evidence/task-11-status-section.txt
  ```

  **Evidence to Capture:**
  - [ ] task-11-doc-references.txt
  - [ ] task-11-status-section.txt

  **Commit**: YES (group 8, with Task 10)
  - Message: `test(hil): verify refactored controller with existing test suite`
  - Files: `docs/hil-architecture.md` (corrections only)
  - Pre-commit: QA scenarios pass

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run linter if configured. Review all changed/new files for: `as any`/`@ts-ignore` equivalents in Python (bare except, # type: ignore), empty catches, print() in production paths, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real QA — Full Test Suite** — `unspecified-high`
  Start from clean state. Build simulator with `make unix`. Run `python3 run_tests.py` (simulator mode) and verify ALL tests pass. Then run `python3 run_tests.py --hardware --port mock` (or simulator fallback) to verify the hardware path doesn't crash. Save all output.
  Output: `Sim Tests [N/N pass] | HW Path [smoke OK/FAIL] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built, nothing beyond spec. Check "Must NOT do" compliance: no modified test files, no UART baud changes, no CI config. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Commit | Tasks | Message | Key Files |
|--------|-------|---------|-----------|
| 1 | T1 | `docs(hil): add hardware-in-the-loop testing architecture document` | `docs/hil-architecture.md` |
| 2 | T2, T8 | `refactor(test): extract BaseController ABC from SimController` | `test/integration/util/base_controller.py`, `test/integration/util/controller.py` |
| 3 | T3 | `feat(test): add STLinkManager for hardware lifecycle control` | `test/integration/util/stlink_manager.py` |
| 4 | T4 | `feat(firmware): extend TestMode to listen on UART3 VCP at 115200` | `src/test_mode.py` |
| 5 | T5, T6 | `feat(test): add UARTChannel and command protocol mapping` | `test/integration/util/uart_channel.py`, `test/integration/util/protocol.py` |
| 6 | T7 | `feat(test): implement HardwareController for HIL testing` | `test/integration/util/hardware_controller.py` |
| 7 | T9 | `feat(test): add --hardware flag to test runner and Makefile targets` | `test/integration/run_tests.py`, `Makefile` |
| 8 | T10, T11 | `test(hil): verify refactored controller with existing test suite` | evidence files |

---

## Success Criteria

### Verification Commands
```bash
# Existing tests still pass (no regression)
cd test/integration && python3 run_tests.py
# Expected: All tests pass

# Hardware controller module imports without error
python3 -c "from util.hardware_controller import HardwareController"
# Expected: No import error (run from test/integration/)

# BaseController ABC is properly structured
python3 -c "from util.base_controller import BaseController; print(BaseController.__abstractmethods__)"
# Expected: frozenset({'start', 'load', 'shutdown', 'query'})

# Architecture doc exists and has all sections
grep -c "^##" docs/hil-architecture.md
# Expected: >= 10 sections

# TestMode UART code present in firmware
grep "UART\|uart" src/test_mode.py
# Expected: UART listener code present

# Make target exists
make -n test-hil
# Expected: Recipe shown (not "No rule to make target")
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Existing simulator tests pass unchanged
- [ ] Architecture document covers all 10 requested sections
- [ ] HardwareController has same query(data, commands=[]) interface as SimController
- [ ] TestMode responds on UART channel
