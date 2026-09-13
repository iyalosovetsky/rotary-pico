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

# Comm-result and error-bit codes, and their messages, match the official
# Waveshare/Feetech scservo_sdk (protocol_packet_handler.py) so status
# reports here read the same way as the vendored STServo_Python demos.
COMM_SUCCESS = 0
COMM_RX_TIMEOUT = -6
COMM_RX_CORRUPT = -7

ERRBIT_VOLTAGE = 1
ERRBIT_ANGLE = 2
ERRBIT_OVERHEAT = 4
ERRBIT_OVERELE = 8
ERRBIT_OVERLOAD = 32


def get_result_text(result):
    if result == COMM_SUCCESS:
        return "[TxRxResult] Communication success!"
    if result == COMM_RX_TIMEOUT:
        return "[TxRxResult] There is no status packet!"
    if result == COMM_RX_CORRUPT:
        return "[TxRxResult] Incorrect status packet!"
    return "[TxRxResult] Unknown result %d" % result


def get_error_text(error):
    msgs = []
    if error & ERRBIT_VOLTAGE:
        msgs.append("Input voltage error!")
    if error & ERRBIT_ANGLE:
        msgs.append("Angle sen error!")
    if error & ERRBIT_OVERHEAT:
        msgs.append("Overheat error!")
    if error & ERRBIT_OVERELE:
        msgs.append("OverEle error!")
    if error & ERRBIT_OVERLOAD:
        msgs.append("Overload error!")
    return "[ServoStatus] " + " ".join(msgs) if msgs else ""


ADDR_MODEL_L = 3
ADDR_MIN_ANGLE_LIMIT_L = 9
ADDR_MAX_ANGLE_LIMIT_L = 11
ADDR_MODE = 33
ADDR_TORQUE_ENABLE = 40
ADDR_ACC = 41
ADDR_GOAL_POSITION_L = 42
ADDR_GOAL_TIME_L = 44
ADDR_GOAL_SPEED_L = 46
ADDR_PRESENT_POSITION_L = 56
ADDR_PRESENT_LOAD_L = 60
ADDR_PRESENT_VOLTAGE = 62
ADDR_PRESENT_TEMPERATURE = 63
ADDR_MOVING = 66
ADDR_PRESENT_CURRENT_L = 69

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
        """Low-level transaction. Returns (reply_bytes, comm_result, error_byte),
        mirroring the official SDK's (data, comm_result, error) shape."""
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
            return b"", COMM_SUCCESS, 0

        reply = self._read_exact(reply_len)
        if len(reply) < reply_len:
            return reply, COMM_RX_TIMEOUT, 0
        if reply[0] != 0xFF or reply[1] != 0xFF or reply[2] != servo_id:
            return reply, COMM_RX_CORRUPT, 0
        checksum = (~sum(reply[2:-1])) & 0xFF
        if reply[-1] != checksum:
            return reply, COMM_RX_CORRUPT, 0
        return reply, COMM_SUCCESS, reply[4]

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

    # -- verbose, status-returning API (mirrors the official scservo_sdk) --

    def ping_status(self, servo_id):
        """Returns (comm_result, error_byte)."""
        _, result, error = self._txrx(servo_id, INST_PING, b"", reply_len=6)
        return result, error

    def read_status(self, servo_id, addr, length):
        """Returns (data_bytes_or_None, comm_result, error_byte)."""
        params = bytes([addr, length])
        reply, result, error = self._txrx(servo_id, INST_READ, params, reply_len=6 + length)
        data = bytes(reply[5:5 + length]) if result == COMM_SUCCESS else None
        return data, result, error

    def write_status(self, servo_id, addr, data):
        """Returns (comm_result, error_byte)."""
        params = bytes([addr]) + bytes(data)
        _, result, error = self._txrx(servo_id, INST_WRITE, params, reply_len=6)
        return result, error

    # -- simple API used by ST3215/scanner_rig.py: bool / raise on failure --

    def write(self, servo_id, addr, data):
        result, error = self.write_status(servo_id, addr, data)
        if result != COMM_SUCCESS:
            raise OSError("servo %d: %s" % (servo_id, get_result_text(result)))

    def read(self, servo_id, addr, length):
        data, result, error = self.read_status(servo_id, addr, length)
        if result != COMM_SUCCESS:
            raise OSError("servo %d: %s" % (servo_id, get_result_text(result)))
        return data

    def ping(self, servo_id):
        result, error = self.ping_status(servo_id)
        return result == COMM_SUCCESS


class ST3215:
    def __init__(self, bus, servo_id):
        self.bus = bus
        self.id = servo_id

    def ping(self):
        return self.bus.ping(self.id)

    def ping_verbose(self):
        """Like the official demo's ping(): pings, then reads the model
        number register. Returns (model_number_or_None, comm_result, error)."""
        result, error = self.bus.ping_status(self.id)
        if result != COMM_SUCCESS:
            return None, result, error
        data, result, error = self.bus.read_status(self.id, ADDR_MODEL_L, 2)
        model = (data[0] | (data[1] << 8)) if data else None
        return model, result, error

    def set_goal_verbose(self, position_units, speed=0):
        """Same as set_goal(), but returns (comm_result, error) instead of
        raising on failure."""
        data = [
            position_units & 0xFF, (position_units >> 8) & 0xFF,
            0, 0,
            speed & 0xFF, (speed >> 8) & 0xFF,
        ]
        return self.bus.write_status(self.id, ADDR_GOAL_POSITION_L, data)

    def read_position_verbose(self):
        """Same as read_position(), but returns (position_or_None, comm_result,
        error) instead of raising on failure."""
        data, result, error = self.bus.read_status(self.id, ADDR_PRESENT_POSITION_L, 2)
        pos = (data[0] | (data[1] << 8)) if data else None
        return pos, result, error

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

    def read_voltage(self):
        """Present_Voltage (addr 62, 1 byte): raw * 0.1 = volts (per the
        official Feetech SMS/STS register table)."""
        return self.bus.read(self.id, ADDR_PRESENT_VOLTAGE, 1)[0] * 0.1

    def read_temperature(self):
        """Present_Temperature (addr 63, 1 byte): raw value is already deg C."""
        return self.bus.read(self.id, ADDR_PRESENT_TEMPERATURE, 1)[0]

    def read_load(self):
        """Present_Load (addr 60-61, 2 bytes): bits 0-9 magnitude, bit 10
        direction (per the official register table). Returned as a signed
        raw magnitude (negative = opposite direction) - not independently
        confirmed as a percentage, so left unscaled rather than guessing."""
        raw = self.bus.read(self.id, ADDR_PRESENT_LOAD_L, 2)
        value = raw[0] | (raw[1] << 8)
        magnitude = value & 0x3FF
        return -magnitude if (value & 0x400) else magnitude

    def read_current_ma(self):
        """Present_Current (addr 69-70, 2 bytes): raw * 6.5 = mA (per the
        official Feetech SMS/STS register table)."""
        raw = self.bus.read(self.id, ADDR_PRESENT_CURRENT_L, 2)
        return (raw[0] | (raw[1] << 8)) * 6.5

    def diag_summary(self):
        """Human-readable servo health check: voltage/temperature/load/
        current plus the protocol status/error byte that comes back with
        every reply (see ERRBIT_* above) - decoded the same way the
        TMC2209 driver's diag_summary() reports ERROR(...) flags, for a
        consistent "<axis> TMC" command across every axis. Meant for an
        interactive console status command, not programmatic decisions.
        """
        data, result, error = self.bus.read_status(self.id, ADDR_PRESENT_VOLTAGE, 1)
        if result != COMM_SUCCESS:
            return "no reply (%s)" % get_result_text(result)
        voltage = data[0] * 0.1
        temperature = self.read_temperature()
        load = self.read_load()
        current_ma = self.read_current_ma()
        moving = "yes" if self.is_moving() else "no"

        flags = []
        if error & ERRBIT_VOLTAGE:
            flags.append("VOLTAGE")
        if error & ERRBIT_ANGLE:
            flags.append("ANGLE")
        if error & ERRBIT_OVERHEAT:
            flags.append("OVERHEAT")
        if error & ERRBIT_OVERELE:
            flags.append("OVERELE")
        if error & ERRBIT_OVERLOAD:
            flags.append("OVERLOAD")
        status = "OK" if not flags else "ERROR(%s)" % ",".join(flags)
        return "%s voltage=%.3gV temp=%dC load=%d current=%.4gmA moving=%s" % (
            status, voltage, temperature, load, current_ma, moving)
