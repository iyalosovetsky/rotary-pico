"""MicroPython UART driver for TMC2209 stepper drivers.

Written for the BTT SKR Pico wiring: all 4 drivers share one UART bus
(TX=gpio8 through a 1k resistor, RX=gpio9 wired directly to PDN_UART),
distinguished by a node address set via each driver's MS1/MS2 pins.
Because TX and RX are tied to the same physical wire, every byte we
send is also echoed back on RX - that echo has to be drained before
reading a real reply.
"""

from machine import UART, Pin
import time

SYNC = 0x05
MASTER_ADDR = 0xFF

REG_GCONF = 0x00
REG_GSTAT = 0x01
REG_IOIN = 0x06
REG_IHOLD_IRUN = 0x10
REG_TPWMTHRS = 0x13
REG_CHOPCONF = 0x6C
REG_DRV_STATUS = 0x6F

# uart_address values from printer.cfg
ADDR_X = 0
ADDR_Z = 1
ADDR_Y = 2
ADDR_E = 3

_MRES_TABLE = {256: 0, 128: 1, 64: 2, 32: 3, 16: 4, 8: 5, 4: 6, 2: 7, 1: 8}


def _crc8(data):
    crc = 0
    for byte in data:
        for _ in range(8):
            if (crc >> 7) ^ (byte & 1):
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
            byte >>= 1
    return crc


class TMC2209Bus:
    """One shared UART bus - pass the same instance to every TMC2209() below."""

    def __init__(self, uart_id=1, tx=8, rx=9, baudrate=40000):
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx), rx=Pin(rx),
                          timeout=20, timeout_char=5)

    def write_register(self, address, reg, value):
        dg = bytearray(8)
        dg[0] = SYNC
        dg[1] = address
        dg[2] = reg | 0x80
        dg[3] = (value >> 24) & 0xFF
        dg[4] = (value >> 16) & 0xFF
        dg[5] = (value >> 8) & 0xFF
        dg[6] = value & 0xFF
        dg[7] = _crc8(dg[:7])
        self.uart.write(dg)
        self._read_exact(len(dg))  # drain our own echo

    def read_register(self, address, reg):
        req = bytearray(4)
        req[0] = SYNC
        req[1] = address
        req[2] = reg & 0x7F
        req[3] = _crc8(req[:3])
        self.uart.write(req)
        self._read_exact(len(req))  # drain our own echo

        reply = self._read_exact(8)
        if len(reply) < 8:
            raise OSError("TMC2209 addr %d reg 0x%02X: no reply (check wiring/address)" % (address, reg))
        if reply[0] != SYNC or reply[1] != MASTER_ADDR or reply[2] != reg:
            raise OSError("TMC2209 addr %d reg 0x%02X: bad reply header %r" % (address, reg, reply))
        if _crc8(reply[:7]) != reply[7]:
            raise OSError("TMC2209 addr %d reg 0x%02X: CRC mismatch" % (address, reg))
        return (reply[3] << 24) | (reply[4] << 16) | (reply[5] << 8) | reply[6]

    def _read_exact(self, n, budget_ms=50):
        buf = bytearray()
        deadline = time.ticks_add(time.ticks_ms(), budget_ms)
        while len(buf) < n and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            chunk = self.uart.read(n - len(buf))
            if chunk:
                buf += chunk
            else:
                time.sleep_ms(1)
        return buf


class TMC2209:
    def __init__(self, bus, address, step_pin, dir_pin, en_pin=None,
                 rsense=0.11, vsense=False):
        self.bus = bus
        self.address = address
        self.rsense = rsense
        self.vsense = vsense
        self.step = Pin(step_pin, Pin.OUT, value=0)
        self.dir = Pin(dir_pin, Pin.OUT, value=0)
        # EN is active-low on the TMC2209 (matches the "!" in your printer.cfg enable_pin)
        self.en = Pin(en_pin, Pin.OUT, value=1) if en_pin is not None else None

    def write(self, reg, value):
        self.bus.write_register(self.address, reg, value)

    def read(self, reg):
        return self.bus.read_register(self.address, reg)

    def check_connection(self):
        ioin = self.read(REG_IOIN)
        version = (ioin >> 24) & 0xFF
        if version != 0x21:
            raise OSError("addr %d: unexpected IOIN version 0x%02X (expected 0x21)" % (self.address, version))
        return True

    def enable_uart_mode(self, spreadcycle=False):
        gconf = (1 << 6) | (1 << 7)  # pdn_disable + mstep_reg_select, required for UART operation
        if spreadcycle:
            gconf |= (1 << 2)
        self.write(REG_GCONF, gconf)

    def set_current(self, run_ma, hold_ma=None, hold_delay=10):
        if hold_ma is None:
            hold_ma = run_ma // 2
        vfs = 0.180 if self.vsense else 0.325

        def to_cs(ma):
            i = ma / 1000.0
            cs = int(round(32.0 * 1.41421356 * i * (self.rsense + 0.02) / vfs - 1))
            return max(0, min(31, cs))

        irun = to_cs(run_ma)
        ihold = to_cs(hold_ma)
        value = (ihold & 0x1F) | ((irun & 0x1F) << 8) | ((hold_delay & 0xF) << 16)
        self.write(REG_IHOLD_IRUN, value)

    def set_microsteps(self, microsteps=256):
        if microsteps not in _MRES_TABLE:
            raise ValueError("microsteps must be one of %s" % sorted(_MRES_TABLE))
        chopconf = self.read(REG_CHOPCONF)
        chopconf &= ~(0xF << 24)
        chopconf |= (_MRES_TABLE[microsteps] << 24)
        self.write(REG_CHOPCONF, chopconf)

    def enable_driver(self, enabled=True):
        if self.en is not None:
            self.en.value(0 if enabled else 1)

    def move(self, steps, step_delay_us=800):
        """Simple blocking STEP/DIR move - fine for bench testing."""
        self.dir.value(1 if steps >= 0 else 0)
        time.sleep_us(5)
        for _ in range(abs(steps)):
            self.step.value(1)
            time.sleep_us(step_delay_us)
            self.step.value(0)
            time.sleep_us(step_delay_us)
