time = __import__("time")
pyb = __import__("pyb")

try:
    stm = __import__("stm")
except Exception:
    stm = None

try:
    machine = __import__("machine")
except Exception:
    machine = None

MARK_BASE = 0x20002000
MARK_MAGIC = 0x534B5052

STATE_BOOT = 0x1001
STATE_OUTPUTS_READY = 0x1002
STATE_UTIL_OK = 0x1010
STATE_CONN_OK = 0x1020
STATE_NO_CARD = 0x1030
STATE_CARD_PRESENT = 0x1040
STATE_T1_OK = 0x1050
STATE_SELECT_DONE = 0x1060
STATE_SUCCESS = 0x9000

ERR_OUTPUT_SETUP = 0xE001
ERR_IMPORT_UTIL = 0xE010
ERR_GET_CONNECTION = 0xE020
ERR_CARD_CHECK = 0xE030
ERR_T1_CONNECT = 0xE040
ERR_SELECT = 0xE050

def init_state_pin(name):
    try:
        p = pyb.Pin(name, pyb.Pin.OUT_PP)
        p.high()
        return p
    except Exception:
        return None


alive_pin = init_state_pin("G6")
card_pin = init_state_pin("D4")
t1_pin = init_state_pin("D5")
ok_pin = init_state_pin("K3")

usb = None
uart_outputs = []


def set_state_pin(pin, active):
    if pin is None:
        return
    try:
        if active:
            pin.low()
        else:
            pin.high()
    except Exception:
        pass


def write_marker(state, arg0, arg1):
    if stm is not None:
        try:
            stm.mem32[MARK_BASE] = MARK_MAGIC
            stm.mem32[MARK_BASE + 4] = state & 0xFFFFFFFF
            stm.mem32[MARK_BASE + 8] = arg0 & 0xFFFFFFFF
            stm.mem32[MARK_BASE + 12] = arg1 & 0xFFFFFFFF
            return
        except Exception:
            pass

    if machine is not None:
        try:
            machine.mem32[MARK_BASE] = MARK_MAGIC
            machine.mem32[MARK_BASE + 4] = state & 0xFFFFFFFF
            machine.mem32[MARK_BASE + 8] = arg0 & 0xFFFFFFFF
            machine.mem32[MARK_BASE + 12] = arg1 & 0xFFFFFFFF
        except Exception:
            pass


def log(msg):
    try:
        print(msg)
    except Exception:
        pass

    if usb is not None:
        try:
            usb.send(msg + "\r\n")
        except Exception:
            pass

    for u in uart_outputs:
        try:
            u.write(msg + "\r\n")
        except Exception:
            pass


write_marker(STATE_BOOT, 0, 0)

try:
    try:
        pyb.usb_mode("VCP")
    except Exception:
        pass

    try:
        usb = pyb.USB_VCP()
    except Exception:
        usb = None

    for uid in (1, 3, 6):
        try:
            u = pyb.UART(uid, 115200)
            uart_outputs.append(u)
        except Exception:
            pass

    write_marker(STATE_OUTPUTS_READY, len(uart_outputs), 0)
except Exception:
    write_marker(ERR_OUTPUT_SETUP, 0, 0)

log("")
log("========================================")
log("SEEDKEEPER PROOF TEST START")
log("Markers @ 0x20002000")
log("========================================")

set_state_pin(alive_pin, True)

attempt = 0
last_sw = 0

while True:
    attempt += 1
    set_state_pin(alive_pin, True)
    log("Attempt " + str(attempt))

    try:
        util = __import__("keystore.javacard.util", None, None, ("get_connection",), 0)
        write_marker(STATE_UTIL_OK, attempt, 0)
    except Exception as e:
        write_marker(ERR_IMPORT_UTIL, attempt, 0)
        log("ERR_IMPORT_UTIL: " + str(e))
        time.sleep(2)
        continue

    try:
        conn = util.get_connection()
        write_marker(STATE_CONN_OK, attempt, 0)
    except Exception as e:
        write_marker(ERR_GET_CONNECTION, attempt, 0)
        log("ERR_GET_CONNECTION: " + str(e))
        time.sleep(2)
        continue

    try:
        present = conn.isCardInserted()
    except Exception as e:
        write_marker(ERR_CARD_CHECK, attempt, 0)
        log("ERR_CARD_CHECK: " + str(e))
        time.sleep(2)
        continue

    if not present:
        set_state_pin(card_pin, False)
        set_state_pin(t1_pin, False)
        set_state_pin(ok_pin, False)
        write_marker(STATE_NO_CARD, attempt, 0)
        log("NO_CARD")
        time.sleep(2)
        continue

    set_state_pin(card_pin, True)
    write_marker(STATE_CARD_PRESENT, attempt, 1)
    log("CARD_PRESENT")

    try:
        conn.connect(conn.T1_protocol)
        set_state_pin(t1_pin, True)
        write_marker(STATE_T1_OK, attempt, 1)
        log("T1_CONNECTED")
    except Exception as e:
        set_state_pin(t1_pin, False)
        set_state_pin(ok_pin, False)
        write_marker(ERR_T1_CONNECT, attempt, 0)
        log("ERR_T1_CONNECT: " + str(e))
        time.sleep(2)
        continue

    try:
        aid = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
        _resp, sw1, sw2 = conn.sendAPDU(0xB0, 0xA4, 0x04, 0x00, aid)
        last_sw = ((sw1 << 8) | sw2)
        write_marker(STATE_SELECT_DONE, last_sw, attempt)
        log("SELECT_SW=" + hex(last_sw))

        if last_sw == 0x9000:
            set_state_pin(ok_pin, True)
            write_marker(STATE_SUCCESS, last_sw, attempt)
            log("SEEDKEEPER_SELECT_OK")
        else:
            set_state_pin(ok_pin, False)
    except Exception as e:
        set_state_pin(ok_pin, False)
        write_marker(ERR_SELECT, attempt, 0)
        log("ERR_SELECT: " + str(e))

    time.sleep(2)
