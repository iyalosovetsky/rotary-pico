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
    X MOVE <deg>                one-shot relative rotation (signed), axis must
                                 be stopped first - see below
    X ZERO                      make the current position 0 - see below
    X TMC                       TMC2209 driver health (faults/temp/current) - see below

    Y MIN <steps>
    Y MAX <steps>
    Y SPEED <steps_per_sec>     unsigned
    Y SGTHRS <0-255>            StallGuard sensorless-homing threshold, needs tuning
    Y HOME [DEC|INC] [speed]    home toward a StallGuard stall - see below
    Y LEAD <mm>                 lead screw pitch (mm per screw revolution), for MOVE
    Y MOVE <mm>                 one-shot relative move (signed) - see below
    Y ZERO                      make the current position 0 - see below
    Y TMC                       TMC2209 driver health (faults/temp/current) - see below
    Y START
    Y STOP

    Z MIN <steps>
    Z MAX <steps>
    Z SPEED <steps_per_sec>     unsigned
    Z SGTHRS <0-255>            StallGuard sensorless-homing threshold, needs tuning
    Z HOME [DEC|INC] [speed]    home toward a StallGuard stall - see below
    Z LEAD <mm>                 lead screw pitch (mm per screw revolution), for MOVE
    Z MOVE <mm>                 one-shot relative move (signed) - see below
    Z ZERO                      make the current position 0 - see below
    Z TMC                       TMC2209 driver health (faults/temp/current) - see below
    Z START
    Z STOP

Y and Z have no physical endstops - HOME finds the mechanical limit via
the TMC2209's StallGuard: SG_RESULT is polled over UART (~every 100ms)
during the homing move, using a reduced current and forced spreadCycle
just for that move, since StallGuard's signal is too noisy under
stealthChop to trust otherwise (see TROUBLESHOOTING.md). HOME
deliberately drives toward one end (DEC = decreasing position, INC =
increasing) until SG_RESULT drops below SGTHRS, then makes that stall
point pos=0 (MIN or MAX - whichever end it stalled toward - ends up
exactly 0; the other one shifts by the same amount, so it still means
the same real distance from the new zero). Direction/speed given are
remembered (Y defaults to DEC, Z to INC, both at 1000 steps/sec) -
"Y HOME" alone reuses whatever was last set. SGTHRS is a raw SG_RESULT
floor here (not the doubled on-chip register comparison) and needs
tuning by hand for your actual mechanics/speed.

X/Y/Z ZERO does the same zeroing HOME does (current pos becomes 0,
MIN/MAX shift to match), but instantly and wherever the axis currently
is - no motion, no StallGuard involved. Use it to redefine the origin
by hand instead of (or in addition to) a StallGuard-based HOME - e.g.
X has no HOME at all (continuous rotation, nothing to stall against),
so ZERO is the only way to give it a zero reference.

X/Y/Z TMC reads that driver's own GSTAT/DRV_STATUS registers and
prints a one-line health summary: OK, or ERROR(...) listing any of
RESET/DRV_ERR/UV_CP (GSTAT) or OTPW/OT/S2GA/S2GB/S2VSA/S2VSB/OLA/OLB
(DRV_STATUS) that are set, plus cs_actual (the driver's live current
scale, 0-31), mode (stealthChop/spreadCycle), and standstill. Useful
for diagnosing a motor that's silently drawing less current or running
hotter than expected, without pulling a multimeter. RESET is expected
once right after power-up; GSTAT is cleared after each read so it
doesn't keep reporting an old event as if it just happened.

This is a one-shot calibration, run once before the first START - like
Klipper/Voron-style sensorless homing, ordinary bouncing afterward does
NOT re-check StallGuard on every move (it runs stealthChop at full
current for quiet continuous motion, where the signal isn't reliable
enough to act on).

Y/Z MOVE takes a distance in millimeters, converted to steps via each
axis's LEAD (mm per screw revolution) and this rig's fixed
motor/microstep count. X MOVE takes an angle in degrees instead - X
turns the turntable directly (no screw), so its position is naturally
angular; it's converted to steps the same way, using degrees instead
of mm/lead. Both are one-shot open-loop moves at the axis's configured
SPEED, signed (direction), and require the axis not already
START-ed/bouncing. Y/Z MOVE clamps the target to MIN/MAX so it can't
grind past a homed limit; X has no MIN/MAX (continuous rotation, no
fixed reference) so it isn't clamped.

    A MIN <deg>
    A MAX <deg>
    A SPEED <raw_units>         servo-internal speed register, try 0-1000
    A MOVE <deg>                one-shot relative move (signed), axis must
                                 be stopped first - like Y/Z MOVE but in
                                 degrees, using the servo's own absolute
                                 position feedback instead of open-loop
                                 step counting; clamped to MIN/MAX
    A START
    A STOP

    STATUS                      shows every axis's current position (X/Y/Z in
                                 steps + degrees/mm, A read live from the servo)
                                 alongside its config
    HELP

X/Y/Z have no position sensor - "pos" is just an open-loop step count,
so it's checkpointed to rig_config.json periodically while moving (see
POSITION_AUTOSAVE_INTERVAL_S) and immediately on STOP, to survive a
reboot. A doesn't need this: the ST3215 servo always reports its own
true absolute angle over UART, so STATUS just reads it live instead.

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
# each driver's DIAG output there instead of a mechanical endstop). Not
# currently used for homing - see TROUBLESHOOTING.md: a confirmed-working
# reference detects stalls by polling SG_RESULT over UART instead, which is
# what home_axis() does. Kept declared/wired for future diagnostics. ----
y_diag = Pin(3, Pin.IN, Pin.PULL_DOWN)
z_diag = Pin(25, Pin.IN, Pin.PULL_DOWN)

# ---- servo bus (CHANGE tx/rx to match your actual wiring/adapter!) ----
servo_bus = ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)
servo = ST3215(servo_bus, servo_id=1)

X_CURRENT_MA = 800
Y_CURRENT_MA = 800
Z_CURRENT_MA = 800
HOME_CURRENT_MA = 830  # matches IRUN=14 in a confirmed-working hand-stall test
                        # (google_test_stall_guard.py) on this exact hardware, via
                        # our own current-scale formula. 400 (a generic "lower is
                        # cleaner for homing" guess, not measured on this hardware)
                        # was tried first and computed out to CS~6, far below that.

FULL_STEPS_PER_REV = 200  # standard NEMA17, 1.8deg/step - matches every stepper used here
MICROSTEPS = 16  # matches set_microsteps(MICROSTEPS) in setup_motors
STEPS_PER_REV = FULL_STEPS_PER_REV * MICROSTEPS  # 3200 microsteps/rev - used by MOVE to
                                                  # convert mm (via LEAD)/degrees to steps

CYCLE_DEFAULT_MINUTES = 5
HOME_SPEED_DEFAULT = 1000  # matches a confirmed-working hand-stall test (google_test_stall_guard.py:
                            # 500us pulse half-period = 1kHz). 150, then 500, then 3000 were all
                            # tried first without a confirmed-working reference point to anchor on.
HOME_SAFETY_MAX_STEPS = 20000  # guards against a stall that never trips (bad SGTHRS, broken wiring)

state = {
    "x": {"running": False, "speed": 200, "pos": 0},
    "y": {"running": False, "speed": 400, "min": 0, "max": 3200, "pos": 0, "dir": 1, "sgthrs": 20,
          "home_dir": -1, "home_speed": HOME_SPEED_DEFAULT, "lead_mm": 4.0},
    "z": {"running": False, "speed": 400, "min": 0, "max": 3200, "pos": 0, "dir": 1, "sgthrs": 20,
          "home_dir": 1, "home_speed": HOME_SPEED_DEFAULT, "lead_mm": 4.0},
    "a": {"running": False, "speed": 300, "min_deg": 30, "max_deg": 150},
}

RAMP_START_SPEED = 100  # steps/sec - gentle starting speed for home_axis's ramp-up
RAMP_STEPS = 100  # steps over which home_axis linearly ramps from RAMP_START_SPEED to
                   # the target home speed, before StallGuard checking even begins
STALL_SETTLE_STEPS = 40  # SG_RESULT isn't meaningful until the motor has been moving a
                          # little while - ignore it right after the ramp-up completes
STALL_CONFIRM_COUNT = 3  # cheap insurance against a single noisy SG_RESULT sample -
                          # require this many consecutive ~100ms checks below SGTHRS

# ---- persisted MIN/MAX/SPEED/SGTHRS/HOME_*/POS, saved to/loaded from a file at the board root.
# X/Y/Z's "pos" is the only thing here that isn't a user-set config value - it's the open-loop
# step counter (no position sensor on these axes), persisted so a reboot doesn't forget where
# the mechanism physically is. It's NOT saved on every step (see position_autosave_task) - only
# periodically and at deliberate stops, to avoid hammering the flash. A has no "pos" here: the
# ST3215 servo reports its own true absolute position over UART at any time (read_position_deg),
# so there's nothing open-loop to track/persist for it. ----
CONFIG_FILE = "rig_config.json"
_PERSISTED_FIELDS = {
    "x": ("speed", "pos"),
    "y": ("min", "max", "speed", "sgthrs", "home_dir", "home_speed", "lead_mm", "pos"),
    "z": ("min", "max", "speed", "sgthrs", "home_dir", "home_speed", "lead_mm", "pos"),
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
        m.set_microsteps(MICROSTEPS)
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
            st["pos"] += 1 if st["speed"] > 0 else -1
        else:
            await asyncio.sleep_ms(20)


async def bounce_task(motor, state_key):
    """Drives Y or Z: bounces back and forth between state["min"]/state["max"].

    No live StallGuard/DIAG check here - that only works reliably under
    spreadCycle + reduced current (see home_axis and TROUBLESHOOTING.md),
    not the stealthChop + full run current this uses for quiet continuous
    motion. Establishing MIN/MAX is HOME's job, done once before the first
    START, same as Klipper/Voron-style sensorless homing - not something
    re-checked on every bounce.
    """
    while True:
        st = state[state_key]
        if st["running"]:
            target = st["max"] if st["dir"] == 1 else st["min"]
            if st["pos"] == target:
                st["dir"] *= -1
                target = st["max"] if st["dir"] == 1 else st["min"]
            step_dir = 1 if target > st["pos"] else -1
            motor.dir.value(1 if step_dir > 0 else 0)
            motor.step.value(1)
            time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
            motor.step.value(0)
            period_ms = max(1, int(1000 / max(1, st["speed"])))  # uasyncio here has no sleep_us
            await asyncio.sleep_ms(period_ms)
            st["pos"] += step_dir
        else:
            await asyncio.sleep_ms(20)


def zero_position(state_key):
    """Redefines the axis's current pos as 0. For Y/Z, MIN/MAX shift by the
    same offset so they keep representing the same real physical distance
    from the (new) zero - the mechanism hasn't actually moved, only the
    coordinate labels have. Used by both HOME (zeroes at the stall point)
    and the standalone ZERO command (zeroes wherever the axis is right
    now). Safe to call while the axis is running: it only touches state
    dict entries, no motor I/O, and (uasyncio being cooperative) nothing
    else runs until this function returns, so bounce_task/x_task can't
    observe a half-shifted state.
    """
    st = state[state_key]
    offset = st["pos"]
    st["pos"] = 0
    if "min" in st:
        st["min"] -= offset
    if "max" in st:
        st["max"] -= offset


async def home_axis(motor, state_key):
    """Deliberately drives toward state["home_dir"] at state["home_speed"]
    until SG_RESULT (polled over UART) drops below SGTHRS, then zeroes pos
    at the stall point (MIN/MAX shift along with it, so they keep meaning
    the same real distance from the new zero) and sets MIN (DEC) or MAX
    (INC) to that same zero. Meant for an explicit "Y HOME"/"Z HOME"
    console command, run once before the axis is first START-ed - not
    part of normal bouncing.
    """
    st = state[state_key]
    if st["running"]:
        print(state_key.upper(), "HOME: stop the axis first")
        return

    direction = st["home_dir"]
    speed = st["home_speed"]
    target_period_ms = max(1, int(1000 / max(1, speed)))
    start_period_ms = max(1, int(1000 / RAMP_START_SPEED))
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
        last_check_ms = time.ticks_ms()
        for i in range(HOME_SAFETY_MAX_STEPS):
            # Linear ramp from RAMP_START_SPEED up to the target speed over
            # RAMP_STEPS steps - jumping straight to full speed from a stop
            # can itself cause the motor to briefly miss steps, which looks
            # exactly like a stall to StallGuard.
            if i < RAMP_STEPS:
                period_ms = int(start_period_ms +
                                 (target_period_ms - start_period_ms) * i / RAMP_STEPS)
            else:
                period_ms = target_period_ms
            motor.step.value(1)
            time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
            motor.step.value(0)
            await asyncio.sleep_ms(period_ms)
            st["pos"] += direction
            steps_since_start += 1

            # Polling SG_RESULT is a UART round-trip - too slow to do every step,
            # and (per a confirmed-working reference script) it's what actually
            # detects a real stall reliably here, unlike the DIAG pin (see
            # TROUBLESHOOTING.md). ~100ms matches that reference's cadence.
            if (steps_since_start >= RAMP_STEPS + STALL_SETTLE_STEPS and
                    time.ticks_diff(time.ticks_ms(), last_check_ms) >= 100):
                last_check_ms = time.ticks_ms()
                try:
                    sg = motor.read_stallguard_result()
                    stalled = sg < st["sgthrs"]
                except OSError:
                    stalled = False  # transient UART hiccup - just skip this check
                consecutive_stalls = consecutive_stalls + 1 if stalled else 0
                if consecutive_stalls >= STALL_CONFIRM_COUNT:
                    if direction > 0:
                        st["max"] = st["pos"]
                    else:
                        st["min"] = st["pos"]
                    zero_position(state_key)  # the stall point becomes pos=0
                    save_config()
                    print(state_key.upper(), "homed, pos=0 (SG_RESULT=%d)" % sg)
                    return

        print(state_key.upper(), "HOME failed: StallGuard never tripped after",
              HOME_SAFETY_MAX_STEPS, "steps - check SGTHRS/wiring")
    finally:
        motor.enable_uart_mode(spreadcycle=False)
        motor.set_current(run_current_ma)


async def move_linear_axis(motor, state_key, distance_mm):
    """One-shot relative move of Y/Z by distance_mm (signed), converted to
    steps via the axis's LEAD (mm/screw-revolution) and STEPS_PER_REV.
    Like HOME, requires the axis not already bouncing. Clamps the target to
    MIN/MAX so it can't grind past a homed limit.
    """
    st = state[state_key]
    if st["running"]:
        print(state_key.upper(), "MOVE: stop the axis first")
        return

    steps_per_mm = STEPS_PER_REV / st["lead_mm"]
    target_pos = st["pos"] + round(distance_mm * steps_per_mm)
    clamped_pos = max(st["min"], min(st["max"], target_pos))
    if clamped_pos != target_pos:
        print(state_key.upper(), "MOVE: clamped to MIN/MAX (%d instead of %d)" %
              (clamped_pos, target_pos))
    steps = abs(clamped_pos - st["pos"])
    if steps == 0:
        print(state_key.upper(), "MOVE: distance rounds to 0 steps, nothing to do")
        return
    direction = 1 if clamped_pos > st["pos"] else -1

    speed = max(1, abs(st["speed"]))
    period_ms = max(1, int(1000 / speed))
    motor.dir.value(1 if direction > 0 else 0)
    for _ in range(steps):
        motor.step.value(1)
        time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
        motor.step.value(0)
        await asyncio.sleep_ms(period_ms)
        st["pos"] += direction
    print(state_key.upper(), "moved %.4gmm (%d steps), pos=%d" % (distance_mm, steps, st["pos"]))


async def rotate_x(degrees):
    """One-shot relative rotation of X by degrees (signed), converted to
    steps via STEPS_PER_REV. X has no MIN/MAX (continuous rotation, no
    fixed reference), so unlike move_linear_axis there's nothing to clamp
    against. Requires the axis not already running.
    """
    st = state["x"]
    if st["running"]:
        print("X MOVE: stop the axis first")
        return

    steps = round(abs(degrees) * STEPS_PER_REV / 360.0)
    if steps == 0:
        print("X MOVE: angle rounds to 0 steps, nothing to do")
        return
    direction = 1 if degrees > 0 else -1

    speed = max(1, abs(st["speed"]) or 200)
    period_ms = max(1, int(1000 / speed))
    x_motor.dir.value(1 if direction > 0 else 0)
    for _ in range(steps):
        x_motor.step.value(1)
        time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
        x_motor.step.value(0)
        await asyncio.sleep_ms(period_ms)
        st["pos"] += direction
    print("X moved %.4g deg (%d steps), pos=%d" % (degrees, steps, st["pos"]))


def move_servo(delta_deg):
    """One-shot relative move of A by delta_deg (signed). Unlike Y/Z/X
    (open-loop step counting), the servo reports its own absolute position,
    so this reads that back and issues a single absolute goal instead of
    counting steps. Clamped to MIN/MAX. Requires the axis not already
    bouncing.
    """
    st = state["a"]
    if st["running"]:
        print("A MOVE: stop the axis first")
        return
    try:
        current_deg = servo.read_position_deg()
    except OSError as e:
        print("A MOVE failed: could not read current position -", e)
        return

    target_deg = current_deg + delta_deg
    clamped_deg = max(st["min_deg"], min(st["max_deg"], target_deg))
    if clamped_deg != target_deg:
        print("A MOVE: clamped to MIN/MAX (%.4g instead of %.4g)" % (clamped_deg, target_deg))
    servo.set_goal_deg(clamped_deg, speed=st["speed"])
    print("A moving %.4g -> %.4g deg" % (current_deg, clamped_deg))


POSITION_AUTOSAVE_INTERVAL_S = 10  # how often X/Y/Z's open-loop "pos" is checkpointed to
                                    # flash while it's actually changing (bouncing, spinning,
                                    # or mid-MOVE) - bounds how much a power cut can lose,
                                    # without writing to flash on every single step


async def position_autosave_task():
    last_saved = {key: state[key]["pos"] for key in ("x", "y", "z")}
    while True:
        await asyncio.sleep(POSITION_AUTOSAVE_INTERVAL_S)
        changed = {key: state[key]["pos"] for key in ("x", "y", "z")
                   if state[key]["pos"] != last_saved[key]}
        if changed:
            save_config()
            last_saved.update(changed)


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
    print("X running=%s speed=%d dir=%s pos=%d (%.4gdeg)" %
          (x["running"], x["speed"], "CW" if x["speed"] >= 0 else "CCW",
           x["pos"], x["pos"] * 360.0 / STEPS_PER_REV))
    print("Y running=%s speed=%d min=%d max=%d pos=%d (%.4gmm) sgthrs=%d lead_mm=%.4g" %
          (y["running"], y["speed"], y["min"], y["max"], y["pos"],
           y["pos"] * y["lead_mm"] / STEPS_PER_REV, y["sgthrs"], y["lead_mm"]))
    print("Z running=%s speed=%d min=%d max=%d pos=%d (%.4gmm) sgthrs=%d lead_mm=%.4g" %
          (z["running"], z["speed"], z["min"], z["max"], z["pos"],
           z["pos"] * z["lead_mm"] / STEPS_PER_REV, z["sgthrs"], z["lead_mm"]))
    try:
        a_pos_str = "%.4gdeg" % servo.read_position_deg()
    except OSError:
        a_pos_str = "unknown (servo read failed)"
    print("A running=%s speed=%d min_deg=%d max_deg=%d pos=%s" %
          (a["running"], a["speed"], a["min_deg"], a["max_deg"], a_pos_str))


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
    save_config()  # checkpoint X/Y/Z's pos right away instead of waiting for the next autosave
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
            persist = True  # checkpoint X/Y/Z's pos right away instead of waiting for autosave
        elif sub == "ZERO" and cmd in ("X", "Y", "Z"):
            zero_position(cmd.lower())
            persist = True
        elif sub == "TMC" and cmd in ("X", "Y", "Z"):
            motor = {"X": x_motor, "Y": y_motor, "Z": z_motor}[cmd]
            print(cmd, "TMC:", motor.diag_summary())
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
        elif sub == "LEAD" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["lead_mm"] = float(parts[2])
            persist = True
        elif sub == "MOVE" and len(parts) >= 3 and cmd in ("Y", "Z"):
            motor = y_motor if cmd == "Y" else z_motor
            asyncio.create_task(move_linear_axis(motor, cmd.lower(), float(parts[2])))
        elif sub == "MOVE" and len(parts) >= 3 and cmd == "X":
            asyncio.create_task(rotate_x(float(parts[2])))
        elif sub == "MOVE" and len(parts) >= 3 and cmd == "A":
            move_servo(float(parts[2]))
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
            asyncio.create_task(home_axis(motor, cmd.lower()))
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
    await asyncio.gather(x_task(), bounce_task(y_motor, "y"), bounce_task(z_motor, "z"),
                          servo_task(), console_task(), position_autosave_task())


if __name__ == "__main__":
    asyncio.run(main())
