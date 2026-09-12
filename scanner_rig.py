HELP_TEXT = """Turntable + line-scan + tilt-servo controller for the DIY Creality
Raptor-style 3D scanner rig.

  X = turntable (continuous rotation)
  Y = scanner carriage (bounces between two limits over the table)
  Z = third axis (bounces between two limits, same as Y)
  A = ST3215 servo tilting the scanner head (bounces between two angles)

Console commands (G-code-like, one per line):

    START [minutes]             start ALL axes at once, auto-stop after
                                 [minutes] (default 5) using each axis's
                                 already-configured SPEED/MIN/MAX/etc
    STOP                        stop all axes immediately

    X SPEED <steps_per_sec>     signed: sign sets direction, 0 = stopped
    X START [CW|CCW]           direction optional, defaults to CW (or last-used)
    X STOP

    Y MIN <steps>
    Y MAX <steps>
    Y SPEED <steps_per_sec>     unsigned
    Y SGTHRS <0-255>            StallGuard sensorless-homing threshold, needs tuning
    Y HOME [DEC|INC] [speed]    home toward a StallGuard stall - see below
    Y START
    Y STOP

    Z MIN <steps>
    Z MAX <steps>
    Z SPEED <steps_per_sec>     unsigned
    Z SGTHRS <0-255>            StallGuard sensorless-homing threshold, needs tuning
    Z HOME [DEC|INC] [speed]    home toward a StallGuard stall - see below
    Z START
    Z STOP

Y and Z have no physical endstops - hitting the mechanical limit is
detected via the TMC2209's StallGuard, read through the DIAG pin
(requires the board's switch set to route each driver's DIAG output to
its Y-STOP/Z-STOP header - see PINOUT.md). This is a fast GPIO read,
checked every step; polling SG_RESULT over the shared UART bus instead
was tried first and was too noisy in practice to use directly - see
TROUBLESHOOTING.md. When DIAG trips mid-move, MIN/MAX auto-clamps to
the real position it stalled at and the axis reverses, instead of
grinding against the stop. SGTHRS (0-255, higher trips more easily)
still needs tuning by hand for your actual mechanics/speed via the
UART-side TCOOLTHRS/SGTHRS registers - there's no universal default.

HOME deliberately drives toward one end until it stalls (instead of
waiting for that to happen during normal bouncing), for an initial
calibration before the first START. DEC = decreasing position, INC =
increasing. Direction and speed given are remembered (Y defaults to
DEC, Z to INC, both at 1000 steps/sec) - "Y HOME" alone reuses whatever
was last set. A stall toward DEC sets MIN to that position, toward INC
sets MAX.

    A MIN <deg>
    A MAX <deg>
    A SPEED <raw_units>         servo-internal speed register, try 0-1000
    A START
    A STOP

    STATUS
    HELP

Rename this file to main.py once you're happy with it, to have it run
on boot. Left as scanner_rig.py for now so it doesn't clobber the
existing bench-test main.py.
"""

import sys
import select
import time
import json
from machine import Pin
import uasyncio as asyncio

from tmc2209 import TMC2209Bus, TMC2209, ADDR_X, ADDR_Y, ADDR_Z
from st3215 import ServoBus, ST3215

# ---- stepper bus + motors (pins/addresses from printer.cfg) ----
stepper_bus = TMC2209Bus(uart_id=1, tx=8, rx=9, baudrate=40000)
x_motor = TMC2209(stepper_bus, ADDR_X, step_pin=11, dir_pin=10, en_pin=12)
y_motor = TMC2209(stepper_bus, ADDR_Y, step_pin=6, dir_pin=5, en_pin=7)
z_motor = TMC2209(stepper_bus, ADDR_Z, step_pin=19, dir_pin=28, en_pin=2)

# ---- StallGuard DIAG pins (Y-STOP/Z-STOP headers, board switch set to route
# each driver's DIAG output there instead of a mechanical endstop) - a fast
# GPIO read, unlike polling SG_RESULT over the shared UART bus every N steps ----
y_diag = Pin(3, Pin.IN, Pin.PULL_DOWN)
z_diag = Pin(25, Pin.IN, Pin.PULL_DOWN)

# ---- servo bus (CHANGE tx/rx to match your actual wiring/adapter!) ----
servo_bus = ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)
servo = ST3215(servo_bus, servo_id=1)

X_CURRENT_MA = 800
Y_CURRENT_MA = 800
Z_CURRENT_MA = 800
HOME_CURRENT_MA = 400  # StallGuard senses more cleanly at a reduced current during
                        # homing specifically (Voron's sensorless-homing guide uses
                        # ~0.49A vs a higher run current) - restored after homing

CYCLE_DEFAULT_MINUTES = 5
HOME_SPEED_DEFAULT = 1000  # matches a confirmed-working hand-stall test (google_test_stall_guard.py:
                            # 500us pulse half-period = 1kHz). 150, then 500, then 3000 were all
                            # tried first without a confirmed-working reference point to anchor on.
HOME_SAFETY_MAX_STEPS = 20000  # guards against a stall that never trips (bad SGTHRS, broken wiring)

state = {
    "x": {"running": False, "speed": 200},
    "y": {"running": False, "speed": 400, "min": 0, "max": 3200, "pos": 0, "dir": 1, "sgthrs": 100,
          "home_dir": -1, "home_speed": HOME_SPEED_DEFAULT},
    "z": {"running": False, "speed": 400, "min": 0, "max": 3200, "pos": 0, "dir": 1, "sgthrs": 100,
          "home_dir": 1, "home_speed": HOME_SPEED_DEFAULT},
    "a": {"running": False, "speed": 300, "min_deg": 30, "max_deg": 150},
}

STALL_SETTLE_STEPS = 40  # the DIAG pin (like SG_RESULT) isn't meaningful until the motor
                          # has been moving a little while - ignore it right after a stop/
                          # reversal, or every reversal false-trips on the ramp-up transient
STALL_CONFIRM_COUNT = 3  # cheap insurance against a single-sample glitch, now that checking
                          # is a plain GPIO read (every step) instead of a UART round-trip.
                          # (Polling SG_RESULT over UART every 10 steps proved too noisy on
                          # real hardware to use directly - see TROUBLESHOOTING.md.)

# ---- persisted MIN/MAX/SPEED/SGTHRS/HOME_*, saved to/loaded from a file at the board root ----
CONFIG_FILE = "rig_config.json"
_PERSISTED_FIELDS = {
    "x": ("speed",),
    "y": ("min", "max", "speed", "sgthrs", "home_dir", "home_speed"),
    "z": ("min", "max", "speed", "sgthrs", "home_dir", "home_speed"),
    "a": ("min_deg", "max_deg", "speed"),
}


def save_config():
    cfg = {axis: {field: state[axis][field] for field in fields}
           for axis, fields in _PERSISTED_FIELDS.items()}
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
    except OSError as e:
        print("WARNING: failed to save", CONFIG_FILE, "-", e)


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        print("loaded", CONFIG_FILE)
    except (OSError, ValueError):
        cfg = {}  # no config file yet, or it's corrupt - fall through to write the defaults

    missing_defaults = False
    for axis, fields in _PERSISTED_FIELDS.items():
        saved = cfg.get(axis, {})
        state[axis].update(saved)
        if any(field not in saved for field in fields):
            missing_defaults = True  # new field (or a brand new file) - persist the default

    if missing_defaults:
        save_config()
        print("saved defaults for missing", CONFIG_FILE, "fields")


load_config()


def setup_motors():
    for m, current in ((x_motor, X_CURRENT_MA), (y_motor, Y_CURRENT_MA), (z_motor, Z_CURRENT_MA)):
        m.check_connection()
        m.enable_uart_mode(spreadcycle=False)
        m.set_current(current)
        m.set_microsteps(16)
        m.enable_driver(True)
    # TCOOLTHRS is a MINIMUM-speed threshold: DIAG/StallGuard switches ON
    # above that speed (Trinamic datasheet: "lower threshold velocity for
    # switching on..."). Max value = active at any practical speed. (An
    # earlier attempt set this low thinking it meant the opposite, which
    # likely disabled DIAG entirely at our real bounce/home speeds - see
    # TROUBLESHOOTING.md.)
    y_motor.enable_stallguard(state["y"]["sgthrs"], tcoolthrs=0xFFFFF)
    z_motor.enable_stallguard(state["z"]["sgthrs"], tcoolthrs=0xFFFFF)
    print("X/Y/Z drivers ready")

    if servo.ping():
        servo.torque_enable(True)
        print("servo ready")
    else:
        print("WARNING: servo did not respond to ping - check wiring/id, A commands will fail")


# ---------------- motion tasks ----------------

async def x_task():
    while True:
        st = state["x"]
        if st["running"] and st["speed"] != 0:
            x_motor.dir.value(1 if st["speed"] > 0 else 0)
            x_motor.step.value(1)
            time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
            x_motor.step.value(0)
            period_ms = max(1, int(1000 / abs(st["speed"])))  # uasyncio here has no sleep_us
            await asyncio.sleep_ms(period_ms)
        else:
            await asyncio.sleep_ms(20)


async def bounce_task(motor, state_key, diag_pin):
    """Drives Y or Z: bounces back and forth between state["min"]/state["max"].

    No physical endstops - the TMC2209 DIAG pin (wired to the Y-STOP/Z-STOP
    header via the board's switch) stands in for one: a real stall pulls it
    high. Checked every step (it's a plain GPIO read, unlike polling
    SG_RESULT over UART - see TROUBLESHOOTING.md for why that wasn't good
    enough on its own). A confirmed stall clamps MIN/MAX to wherever it
    actually happened and reverses, instead of grinding against the stop.
    """
    steps_since_reversal = 0
    consecutive_stalls = 0
    while True:
        st = state[state_key]
        if st["running"]:
            target = st["max"] if st["dir"] == 1 else st["min"]
            if st["pos"] == target:
                st["dir"] *= -1
                target = st["max"] if st["dir"] == 1 else st["min"]
                steps_since_reversal = 0
                consecutive_stalls = 0
            step_dir = 1 if target > st["pos"] else -1
            motor.dir.value(1 if step_dir > 0 else 0)
            motor.step.value(1)
            time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
            motor.step.value(0)
            period_ms = max(1, int(1000 / max(1, st["speed"])))  # uasyncio here has no sleep_us
            await asyncio.sleep_ms(period_ms)
            st["pos"] += step_dir
            steps_since_reversal += 1

            if steps_since_reversal >= STALL_SETTLE_STEPS:
                consecutive_stalls = consecutive_stalls + 1 if diag_pin.value() else 0
                if consecutive_stalls >= STALL_CONFIRM_COUNT:
                    print(state_key.upper(), "DIAG tripped at pos=%d (%s)" %
                          (st["pos"], "MAX" if step_dir > 0 else "MIN"))
                    if step_dir > 0:
                        st["max"] = st["pos"]
                    else:
                        st["min"] = st["pos"]
                    st["dir"] *= -1
                    steps_since_reversal = 0
                    consecutive_stalls = 0
                    save_config()
        else:
            steps_since_reversal = 0
            consecutive_stalls = 0
            await asyncio.sleep_ms(20)


async def home_axis(motor, state_key, diag_pin):
    """Deliberately drives toward state["home_dir"] at state["home_speed"]
    until the DIAG pin trips, then sets MIN (DEC) or MAX (INC) to where it
    stopped. Meant for an explicit "Y HOME"/"Z HOME" console command, run
    once before the axis is first START-ed - not part of normal bouncing.
    """
    st = state[state_key]
    if st["running"]:
        print(state_key.upper(), "HOME: stop the axis first")
        return

    direction = st["home_dir"]
    speed = st["home_speed"]
    period_ms = max(1, int(1000 / max(1, speed)))
    motor.dir.value(1 if direction > 0 else 0)
    print(state_key.upper(), "homing %s at %d steps/sec..." %
          ("INC" if direction > 0 else "DEC", speed))

    # stealthChop (used for normal quiet bouncing) is known to make
    # StallGuard readings noisy/unreliable; spreadCycle gives a clean signal
    # for homing. Reduced current also senses more cleanly during homing
    # than the normal run current. Both are always restored afterward.
    run_current_ma = Y_CURRENT_MA if state_key == "y" else Z_CURRENT_MA
    motor.enable_uart_mode(spreadcycle=True)
    motor.set_current(HOME_CURRENT_MA)
    try:
        steps_since_start = 0
        consecutive_stalls = 0
        for _ in range(HOME_SAFETY_MAX_STEPS):
            motor.step.value(1)
            time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
            motor.step.value(0)
            await asyncio.sleep_ms(period_ms)
            st["pos"] += direction
            steps_since_start += 1

            if steps_since_start >= STALL_SETTLE_STEPS:
                consecutive_stalls = consecutive_stalls + 1 if diag_pin.value() else 0
                if consecutive_stalls >= STALL_CONFIRM_COUNT:
                    if direction > 0:
                        st["max"] = st["pos"]
                    else:
                        st["min"] = st["pos"]
                    save_config()
                    print(state_key.upper(), "homed, pos=%d" % st["pos"])
                    return

        print(state_key.upper(), "HOME failed: StallGuard never tripped after",
              HOME_SAFETY_MAX_STEPS, "steps - check SGTHRS/wiring")
    finally:
        motor.enable_uart_mode(spreadcycle=False)
        motor.set_current(run_current_ma)


async def servo_task():
    going_to_max = True
    while True:
        st = state["a"]
        if st["running"]:
            target_deg = st["max_deg"] if going_to_max else st["min_deg"]
            servo.set_goal_deg(target_deg, speed=st["speed"])
            while st["running"]:
                await asyncio.sleep_ms(100)
                try:
                    if not servo.is_moving():
                        break
                except OSError:
                    break  # lost comms mid-move - bail out and retry from the top
            going_to_max = not going_to_max
        else:
            await asyncio.sleep_ms(50)


# ---------------- console ----------------

def print_status():
    x, y, z, a = state["x"], state["y"], state["z"], state["a"]
    print("X running=%s speed=%d dir=%s" %
          (x["running"], x["speed"], "CW" if x["speed"] >= 0 else "CCW"))
    print("Y running=%s speed=%d min=%d max=%d pos=%d sgthrs=%d" %
          (y["running"], y["speed"], y["min"], y["max"], y["pos"], y["sgthrs"]))
    print("Z running=%s speed=%d min=%d max=%d pos=%d sgthrs=%d" %
          (z["running"], z["speed"], z["min"], z["max"], z["pos"], z["sgthrs"]))
    print("A running=%s speed=%d min_deg=%d max_deg=%d" %
          (a["running"], a["speed"], a["min_deg"], a["max_deg"]))


_cycle_task = None


async def _cycle_timer(duration_s):
    await asyncio.sleep(duration_s)
    stop_all()
    print("cycle finished after %.4g min - all axes stopped" % (duration_s / 60))


def start_all(duration_minutes=None):
    global _cycle_task
    if duration_minutes is None:
        duration_minutes = CYCLE_DEFAULT_MINUTES
    for key in ("x", "y", "z", "a"):
        state[key]["running"] = True
    if _cycle_task is not None:
        _cycle_task.cancel()
    _cycle_task = asyncio.create_task(_cycle_timer(duration_minutes * 60))
    print("ok START - all axes running, cycle length %.4g min" % duration_minutes)


def stop_all():
    for key in ("x", "y", "z", "a"):
        state[key]["running"] = False
    print("ok STOP - all axes stopped")


def handle_command(line):
    """Never raises - any failure below is reported to the console instead
    of propagating up through console_task and killing asyncio.gather()
    (and with it every other axis's motion, not just the console)."""
    try:
        _dispatch_command(line)
    except Exception as e:
        print("? command failed (%s):" % type(e).__name__, e, "-", line)


def _dispatch_command(line):
    parts = line.strip().split()
    if not parts:
        return
    cmd = parts[0].upper()

    if cmd == "STATUS":
        print_status()
        return
    if cmd == "HELP":
        print(HELP_TEXT)
        return
    if cmd == "START":
        try:
            duration = float(parts[1]) if len(parts) >= 2 else None
        except ValueError:
            print("? bad duration (minutes):", line)
            return
        start_all(duration)
        return
    if cmd == "STOP":
        stop_all()
        return

    if cmd not in ("X", "Y", "Z", "A") or len(parts) < 2:
        print("? unrecognised command:", line)
        return

    sub = parts[1].upper()
    axis = {"X": state["x"], "Y": state["y"], "Z": state["z"], "A": state["a"]}[cmd]

    persist = False
    try:
        if sub == "START":
            if cmd == "X" and len(parts) >= 3:
                direction = parts[2].upper()
                magnitude = abs(axis["speed"]) or 200  # speed=0 would never turn the motor
                if direction == "CW":
                    axis["speed"] = magnitude
                elif direction == "CCW":
                    axis["speed"] = -magnitude
                else:
                    print("? bad direction (use CW or CCW):", line)
                    return
                persist = True
            axis["running"] = True
        elif sub == "STOP":
            axis["running"] = False
        elif sub == "SPEED" and len(parts) >= 3:
            axis["speed"] = int(parts[2])
            persist = True
        elif sub == "MIN" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["min"] = int(parts[2])
            persist = True
        elif sub == "MAX" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["max"] = int(parts[2])
            persist = True
        elif sub == "SGTHRS" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["sgthrs"] = int(parts[2])
            persist = True
        elif sub == "HOME" and cmd in ("Y", "Z"):
            idx = 2
            if len(parts) > idx and parts[idx].upper() in ("DEC", "INC"):
                axis["home_dir"] = 1 if parts[idx].upper() == "INC" else -1
                persist = True
                idx += 1
            if len(parts) > idx:
                axis["home_speed"] = int(parts[idx])
                persist = True
            motor = y_motor if cmd == "Y" else z_motor
            diag_pin = y_diag if cmd == "Y" else z_diag
            asyncio.create_task(home_axis(motor, cmd.lower(), diag_pin))
        elif sub == "MIN" and len(parts) >= 3 and cmd == "A":
            axis["min_deg"] = float(parts[2])
            persist = True
        elif sub == "MAX" and len(parts) >= 3 and cmd == "A":
            axis["max_deg"] = float(parts[2])
            persist = True
        else:
            print("? unrecognised command:", line)
            return
    except ValueError:
        print("? bad numeric value:", line)
        return

    print("ok", line)
    if persist:
        save_config()


async def console_task():
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    buf = ""
    while True:
        if poller.poll(0):
            ch = sys.stdin.read(1)
            if ch in ("\n", "\r"):
                if buf.strip():
                    handle_command(buf)
                buf = ""
            else:
                buf += ch
        else:
            await asyncio.sleep_ms(20)


async def main():
    setup_motors()
    print_status()
    print("ready - type HELP for commands")
    await asyncio.gather(x_task(), bounce_task(y_motor, "y", y_diag), bounce_task(z_motor, "z", z_diag),
                          servo_task(), console_task())


if __name__ == "__main__":
    asyncio.run(main())
