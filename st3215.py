"""MicroPython driver for Feetech/Waveshare ST3215 serial bus servo
(SMS/STS protocol - verified against the official ftservo/FTServo_Python
and parallax/scservo SDKs: packet format, instruction opcodes and the
register table below are taken directly from those sources).

The servo itself is single-wire half-duplex. A plain MCU UART has
separate TX/RX pins, so you need a small transceiver between them and
the servo's signal wire (e.g. Waveshare's "Bus Servo Adapter" board, or
a one-transistor combiner).

Unlike the TMC2209 bus (tmc2209.py), where TX is wired straight into RX
through a resistor and every transmitted byte genuinely echoes back, the
Waveshare adapter is a real transceiver: our TX and RX stay electrically
separate right up to the adapter, so there is no self-echo to drain here.
Draining for one anyway would (and did) swallow the servo's real reply,
since it can arrive within microseconds of the request - faster than a
drain read times out.
"""

from machine import UART, Pin
import time

HEADER = b"\xFF\xFF"

INST_PING = 1
INST_READ = 2
INST_WRITE = 3

ADDR_MIN_ANGLE_LIMIT_L = 9
ADDR_MAX_ANGLE_LIMIT_L = 11
ADDR_MODE = 33
ADDR_TORQUE_ENABLE = 40
ADDR_ACC = 41
ADDR_GOAL_POSITION_L = 42
ADDR_GOAL_TIME_L = 44
ADDR_GOAL_SPEED_L = 46
ADDR_PRESENT_POSITION_L = 56
ADDR_MOVING = 66

UNITS_PER_REV = 4096  # 12-bit position, 360 degrees full turn


def deg_to_units(deg):
    return max(0, min(UNITS_PER_REV - 1, int(round(deg / 360.0 * UNITS_PER_REV))))


def units_to_deg(units):
    return units * 360.0 / UNITS_PER_REV


class ServoBus:
    def __init__(self, uart_id=0, tx=0, rx=1, baudrate=1000000):
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx), rx=Pin(rx),
                          timeout=20, timeout_char=5)

    def _txrx(self, servo_id, instruction, params, reply_len):
        length = len(params) + 2
        pkt = bytearray()
        pkt += HEADER
        pkt.append(servo_id)
        pkt.append(length)
        pkt.append(instruction)
        pkt += bytes(params)
        checksum = (servo_id + length + instruction + sum(params)) & 0xFF
        pkt.append((~checksum) & 0xFF)
        self.uart.write(pkt)
        if reply_len == 0:
            return b""
        return self._read_exact(reply_len)

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

    def write(self, servo_id, addr, data):
        params = bytes([addr]) + bytes(data)
        self._txrx(servo_id, INST_WRITE, params, reply_len=6)

    def read(self, servo_id, addr, length):
        params = bytes([addr, length])
        reply = self._txrx(servo_id, INST_READ, params, reply_len=6 + length)
        if len(reply) < 6 + length:
            raise OSError("servo %d: no reply reading addr %d (check wiring/id)" % (servo_id, addr))
        return reply[5:5 + length]

    def ping(self, servo_id):
        reply = self._txrx(servo_id, INST_PING, b"", reply_len=6)
        return len(reply) == 6 and reply[0] == 0xFF and reply[1] == 0xFF and reply[2] == servo_id


class ST3215:
    def __init__(self, bus, servo_id):
        self.bus = bus
        self.id = servo_id

    def ping(self):
        return self.bus.ping(self.id)

    def torque_enable(self, enabled=True):
        self.bus.write(self.id, ADDR_TORQUE_ENABLE, [1 if enabled else 0])

    def set_acceleration(self, acc):
        """Raw register units (0-254). Exact accel-per-unit isn't documented
        consistently - leave alone unless you want to experiment."""
        self.bus.write(self.id, ADDR_ACC, [acc & 0xFF])

    def set_goal(self, position_units, speed=0):
        """speed is a raw servo-internal unit (~0-3400 typical range) - the
        exact deg/sec-per-unit isn't reliably documented, calibrate by eye."""
        data = [
            position_units & 0xFF, (position_units >> 8) & 0xFF,
            0, 0,  # goal time = 0 -> servo uses goal speed instead of a fixed duration
            speed & 0xFF, (speed >> 8) & 0xFF,
        ]
        self.bus.write(self.id, ADDR_GOAL_POSITION_L, data)

    def set_goal_deg(self, deg, speed=0):
        self.set_goal(deg_to_units(deg), speed)

    def read_position(self):
        raw = self.bus.read(self.id, ADDR_PRESENT_POSITION_L, 2)
        return raw[0] | (raw[1] << 8)

    def read_position_deg(self):
        return units_to_deg(self.read_position())

    def is_moving(self):
        raw = self.bus.read(self.id, ADDR_MOVING, 1)
        return raw[0] != 0
