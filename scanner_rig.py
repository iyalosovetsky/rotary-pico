HELP_TEXT = """Turntable + line-scan + tilt-servo controller for the DIY Creality
Raptor-style 3D scanner rig.

  X = turntable (continuous rotation)
  Y = scanner carriage (bounces between two limits over the table)
  Z = third axis (bounces between two limits, same as Y)
  A = ST3215 servo tilting the scanner head (bounces between two angles)

Console commands (G-code-like, one per line):

MIN/MAX/SPEED/SGTHRS/LEAD/MICROSTEPS/CURRENT with no value ("Y MIN",
not "Y MIN 0") prints that field's current value instead of setting it.

    START [minutes]             start ALL axes at once, auto-stop after
                                 [minutes] (default 5) using each axis's
                                 already-configured SPEED/MIN/MAX/etc
    STOP                        stop all axes immediately
    SLEEP                       stop everything, disable X/Y/Z drivers and
                                 release servo torque - see below
    WAKE                        undo SLEEP by hand - see below

    X SPEED <steps_per_sec>     signed: sign sets direction, 0 = stopped
    X START [CW|CCW]           direction optional, defaults to CW (or last-used)
    X STOP
    X MIN <deg>                 default 0 - see below
    X MAX <deg>                 default 180 - see below
    X MOVE <deg|MIN|MAX|MID>    one-shot move - see below
    X ZERO                      make the current position 0 - see below
    X MICROSTEPS <n>             256/128/64/32/16/8/4/2/1 - see below
    X CURRENT <mA>               run current - see below
    X TMC                       TMC2209 driver health (faults/temp/current) - see below

    Y MIN <mm>                   default 0 - lower limit of travel, see below
    Y MAX <mm>                   default 4 - upper limit of travel, see below
    Y SPEED <steps_per_sec>     unsigned
    Y SGTHRS <0-255>            StallGuard sensorless-homing threshold, needs tuning
    Y HOME [DEC|INC] [speed]    home toward a StallGuard stall - see below
    Y LEAD <mm>                 lead screw pitch (mm per screw revolution), for MOVE
    Y MOVE <mm|MIN|MAX|MID>     one-shot move - see below
    Y ZERO                      make the current position 0 - see below
    Y MICROSTEPS <n>             256/128/64/32/16/8/4/2/1 - see below
    Y CURRENT <mA>               run current - see below
    Y TMC                       TMC2209 driver health (faults/temp/current) - see below
    Y START
    Y STOP

    Z MIN <mm>                   default 0 - lower limit of travel, see below
    Z MAX <mm>                   default 4 - upper limit of travel, see below
    Z SPEED <steps_per_sec>     unsigned
    Z SGTHRS <0-255>            StallGuard sensorless-homing threshold, needs tuning
    Z HOME [DEC|INC] [speed]    home toward a StallGuard stall - see below
    Z LEAD <mm>                 lead screw pitch (mm per screw revolution), for MOVE
    Z MOVE <mm|MIN|MAX|MID>     one-shot move - see below
    Z ZERO                      make the current position 0 - see below
    Z MICROSTEPS <n>             256/128/64/32/16/8/4/2/1 - see below
    Z CURRENT <mA>               run current - see below
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
MIN/MAX shift to match - in millimeters for Y/Z, in degrees for X, see
MIN/MAX below), but instantly and wherever the axis currently is - no
motion, no StallGuard involved. Use it to redefine the origin by hand
instead of (or in addition to) a StallGuard-based HOME - e.g. X has no
HOME at all (continuous rotation, nothing to stall against), so ZERO
is the only way to give it a zero reference.

Y/Z MIN/MAX (in millimeters, via LEAD - like MOVE) and X's MIN_DEG/
MAX_DEG (in degrees) are physical units, not steps, so a MICROSTEPS
change never needs to rescale them the way it rescales "pos" itself -
a millimeter or a degree means the same real distance no matter the
microstep resolution, unlike a raw step count. X/Y/Z MICROSTEPS
changes the driver's microstep resolution live (one of
256/128/64/32/16/8/4/2/1) and persists it, rescaling only "pos" by the
resolution ratio so it keeps meaning the same real physical location.
X/Y/Z CURRENT sets that axis's normal run current in mA (hold current
is still derived as half of it, see TMC2209.set_current) and persists
it - separate from HOME_CURRENT_MA, which only applies transiently
during the HOME move itself.

X/Y/Z TMC reads that driver's own GSTAT/DRV_STATUS registers and
prints a one-line health summary: OK, or ERROR(...) listing any of
RESET/DRV_ERR/UV_CP (GSTAT) or OTPW/OT/S2GA/S2GB/S2VSA/S2VSB/OLA/OLB
(DRV_STATUS) that are set, plus current (the driver's live actual
current in mA - IHOLD, not IRUN, while standstill=yes), microsteps
(read back from CHOPCONF, not assumed), mode (stealthChop/spreadCycle),
standstill, and (Y/Z only) sgthrs - shown as "sgthrs=N(cfg)" since
SGTHRS is write-only on this chip (see enable_stallguard/HOME above),
so this is just the value last configured in software, not a hardware
readback. Useful for diagnosing a motor that's silently drawing less
current or running hotter than expected, without pulling a multimeter.
RESET is expected once right after power-up; GSTAT is cleared after
each read so it
doesn't keep reporting an old event as if it just happened.

This is a one-shot calibration, run once before the first START - like
Klipper/Voron-style sensorless homing, ordinary bouncing afterward does
NOT re-check StallGuard on every move (it runs stealthChop at full
current for quiet continuous motion, where the signal isn't reliable
enough to act on).

Y/Z MOVE takes a distance in millimeters, converted to steps via each
axis's LEAD (mm per screw revolution) and its own configured
MICROSTEPS. X MOVE takes an angle in degrees instead - X turns the
turntable directly (no screw), so its position is naturally angular;
it's converted to steps the same way, using degrees instead of
mm/lead. All three are one-shot open-loop moves at the axis's
configured SPEED, signed (direction), and require the axis not already
START-ed/bouncing. Y/Z MOVE clamps the target to MIN/MAX so it can't
grind past a configured limit; a plain numeric X MOVE is deliberately
NOT clamped to its MIN_DEG/MAX_DEG - X is continuous rotation, and
multi-revolution moves like "X MOVE 720" (two full turns) are a
legitimate use case MIN/MAX would only get in the way of.

X/Y/Z/A MOVE also accept MIN, MAX, or MID instead of a number - one-shot
absolute moves straight to that limit (or the midpoint between them),
from wherever the axis currently is, rather than a signed distance
from the current position. This is the only thing X's MIN_DEG/MAX_DEG
(default 0/180, so MID = 90) are used for.

    A MIN <deg>
    A MAX <deg>
    A SPEED <raw_units>         servo-internal speed register, try 0-1000
    A MOVE <deg|MIN|MAX|MID>    one-shot move, axis must be stopped first -
                                 like Y/Z MOVE but in degrees, using the
                                 servo's own absolute position feedback
                                 instead of open-loop step counting;
                                 <deg> is relative and clamped to MIN/MAX
    A TMC                       servo health (voltage/temp/load/current) - see below
    A START
    A STOP

A TMC reads the ST3215's own feedback registers (voltage, temperature,
load, current) plus the status/error byte that comes back with every
reply, decoded the same way X/Y/Z TMC reports ERROR(...) flags: OK, or
ERROR(...) listing any of VOLTAGE/ANGLE/OVERHEAT/OVERELE/OVERLOAD
that are set. load is a raw signed magnitude (not a calibrated
percentage - the servo's own docs don't pin that down precisely).

    STATUS                      shows every axis's current position (X/Y/Z in
                                 steps + degrees/mm, A read live from the servo)
                                 alongside its config, plus whether SLEEPing
    HELP

SLEEP disables the X/Y/Z drivers (EN pin - no holding current at all,
quieter/cooler than just standing still) and releases the servo's
torque, after stopping every axis first. It happens automatically
after SLEEP_TIMEOUT_S (20 minutes by default) of no console input at
all with nothing running, or by typing SLEEP yourself. Any START,
MOVE, or HOME command (for any axis) wakes it back up first, same as
typing WAKE directly. Because a torque-less servo can sag under the
weight of whatever it's holding, waking up compares the servo's
position against what it was right before SLEEP and, if it moved by
more than a degree, commands it back - X/Y/Z don't need this since
their position doesn't drift without power (no significant gravity
load on those axes here).

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

HOME_CURRENT_MA = 830  # matches IRUN=14 in a confirmed-working hand-stall test
                        # (google_test_stall_guard.py) on this exact hardware, via
                        # our own current-scale formula. 400 (a generic "lower is
                        # cleaner for homing" guess, not measured on this hardware)
                        # was tried first and computed out to CS~6, far below that.
                        # Only used transiently during HOME - X/Y/Z's own configured
                        # "current_ma" (see state, CURRENT command) is what's restored
                        # afterward and used for normal bouncing/rotation.

FULL_STEPS_PER_REV = 200  # standard NEMA17, 1.8deg/step - matches every stepper used here
                           # (this one isn't user-configurable - unlike microsteps, it's a
                           # motor property, not a driver setting)


def steps_per_rev(state_key):
    """Microsteps/rev for a given X/Y/Z axis, from its own configurable
    "microsteps" - each axis can run a different resolution (see the
    MICROSTEPS command), so this isn't a single shared constant."""
    return FULL_STEPS_PER_REV * state[state_key]["microsteps"]

CYCLE_DEFAULT_MINUTES = 5
HOME_SPEED_DEFAULT = 1000  # matches a confirmed-working hand-stall test (google_test_stall_guard.py:
                            # 500us pulse half-period = 1kHz). 150, then 500, then 3000 were all
                            # tried first without a confirmed-working reference point to anchor on.
HOME_SAFETY_MAX_STEPS = 20000  # guards against a stall that never trips (bad SGTHRS, broken wiring)

state = {
    # X's MIN/MAX are in degrees (min_deg/max_deg, like A); Y/Z's are in
    # millimeters (min_mm/max_mm, via LEAD) - neither is in steps. Both units
    # are physical/resolution-independent, so a MICROSTEPS change doesn't
    # need to rescale them the way it does "pos" (see set_axis_microsteps),
    # and (for Y/Z) neither does a LEAD change - correcting LEAD changes how
    # many steps a given mm is, not what that mm physically means.
    "x": {"running": False, "speed": 200, "pos": 0, "microsteps": 16, "current_ma": 800,
          "min_deg": 0.0, "max_deg": 180.0},
    "y": {"running": False, "speed": 400, "min_mm": 0.0, "max_mm": 4.0, "pos": 0, "dir": 1,
          "sgthrs": 20, "home_dir": -1, "home_speed": HOME_SPEED_DEFAULT, "lead_mm": 4.0,
          "microsteps": 16, "current_ma": 800},
    "z": {"running": False, "speed": 400, "min_mm": 0.0, "max_mm": 4.0, "pos": 0, "dir": 1,
          "sgthrs": 20, "home_dir": 1, "home_speed": HOME_SPEED_DEFAULT, "lead_mm": 4.0,
          "microsteps": 16, "current_ma": 800},
    "a": {"running": False, "speed": 300, "min_deg": 30, "max_deg": 150},
}

# ---- "<axis> <SUB>" with no value queries that field's current value instead of
# setting it (e.g. "Y MIN" prints Y's min) - maps sub-command -> {cmd: state field}.
# Only for plain value settings; not for START/STOP/ZERO/TMC/HOME/MOVE, which have
# no bare-query meaning of their own. ----
_QUERYABLE_FIELDS = {
    "MIN": {"X": "min_deg", "Y": "min_mm", "Z": "min_mm", "A": "min_deg"},
    "MAX": {"X": "max_deg", "Y": "max_mm", "Z": "max_mm", "A": "max_deg"},
    "SPEED": {"X": "speed", "Y": "speed", "Z": "speed", "A": "speed"},
    "SGTHRS": {"Y": "sgthrs", "Z": "sgthrs"},
    "LEAD": {"Y": "lead_mm", "Z": "lead_mm"},
    "MICROSTEPS": {"X": "microsteps", "Y": "microsteps", "Z": "microsteps"},
    "CURRENT": {"X": "current_ma", "Y": "current_ma", "Z": "current_ma"},
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
    "x": ("speed", "pos", "microsteps", "current_ma", "min_deg", "max_deg"),
    "y": ("min_mm", "max_mm", "speed", "sgthrs", "home_dir", "home_speed", "lead_mm", "pos",
          "microsteps", "current_ma"),
    "z": ("min_mm", "max_mm", "speed", "sgthrs", "home_dir", "home_speed", "lead_mm", "pos",
          "microsteps", "current_ma"),
    "a": ("min_deg", "max_deg", "speed"),
}


def _pretty_json(cfg, indent=2):
    """MicroPython's json.dumps has no indent= option (unlike CPython's),
    so this builds simple indented output by hand for readability when
    inspecting/editing rig_config.json by hand. Only handles the shape
    this config actually has - one level of axis dicts, each a flat
    field:value dict, never deeper - using json.dumps per key/value so
    strings/floats/bools/None are still escaped/formatted correctly.
    """
    lines = ["{"]
    axis_keys = list(cfg.keys())
    for i, axis in enumerate(axis_keys):
        fields = cfg[axis]
        lines.append(" " * indent + json.dumps(axis) + ": {")
        field_keys = list(fields.keys())
        for j, field in enumerate(field_keys):
            comma = "," if j < len(field_keys) - 1 else ""
            lines.append(" " * (indent * 2) + json.dumps(field) + ": " +
                         json.dumps(fields[field]) + comma)
        lines.append(" " * indent + "}" + ("," if i < len(axis_keys) - 1 else ""))
    lines.append("}")
    return "\n".join(lines)


def save_config():
    cfg = {axis: {field: state[axis][field] for field in fields}
           for axis, fields in _PERSISTED_FIELDS.items()}
    try:
        with open(CONFIG_FILE, "w") as f:
            f.write(_pretty_json(cfg))
    except OSError as e:
        print("WARNING: failed to save", CONFIG_FILE, "-", e)


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        print("loaded", CONFIG_FILE)
    except (OSError, ValueError):
        cfg = {}  # no config file yet, or it's corrupt - fall through to write the defaults

    # One-time migration: Y/Z's MIN/MAX used to be raw steps ("min"/"max");
    # they're now millimeters ("min_mm"/"max_mm"). Convert using that axis's
    # own saved lead_mm/microsteps (falling back to today's defaults if
    # either wasn't saved yet) so an existing real HOME calibration keeps
    # meaning the same physical position instead of silently resetting to
    # the mm defaults the first time this runs on an old config file.
    # Forces a save below (via `migrated`) - otherwise the fields-present
    # check right after would see min_mm/max_mm already there and never
    # write the migration back out to CONFIG_FILE.
    migrated = False
    for key in ("y", "z"):
        saved = cfg.get(key, {})
        if "min_mm" not in saved and "min" in saved:
            microsteps = saved.get("microsteps", state[key]["microsteps"])
            lead_mm = saved.get("lead_mm", state[key]["lead_mm"])
            steps_per_mm = (FULL_STEPS_PER_REV * microsteps) / lead_mm
            saved["min_mm"] = saved.pop("min") / steps_per_mm
            saved["max_mm"] = saved.pop("max") / steps_per_mm
            cfg[key] = saved
            migrated = True
            print(key.upper(), "MIN/MAX migrated from steps to mm: min_mm=%.4g max_mm=%.4g" %
                  (saved["min_mm"], saved["max_mm"]))

    missing_defaults = False
    for axis, fields in _PERSISTED_FIELDS.items():
        saved = cfg.get(axis, {})
        state[axis].update(saved)
        if any(field not in saved for field in fields):
            missing_defaults = True  # new field (or a brand new file) - persist the default

    if missing_defaults or migrated:
        save_config()
        print("saved defaults for missing", CONFIG_FILE, "fields")


load_config()


def setup_motors():
    for key, m in (("x", x_motor), ("y", y_motor), ("z", z_motor)):
        m.check_connection()
        m.enable_uart_mode(spreadcycle=False)
        m.set_current(state[key]["current_ma"])
        m.set_microsteps(state[key]["microsteps"])
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
    """Drives Y or Z: bounces back and forth between MIN_MM/MAX_MM,
    converted to steps each iteration since they're kept in millimeters
    (see the state dict comment on why) while pos is in steps.

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
            steps_per_mm = steps_per_rev(state_key) / st["lead_mm"]
            min_pos = round(st["min_mm"] * steps_per_mm)
            max_pos = round(st["max_mm"] * steps_per_mm)
            target = max_pos if st["dir"] == 1 else min_pos
            if st["pos"] == target:
                st["dir"] *= -1
                target = max_pos if st["dir"] == 1 else min_pos
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
    """Redefines the axis's current pos as 0. MIN/MAX shift by the same
    offset (converted to whatever physical unit they're kept in) so they
    keep representing the same real physical position from the (new) zero
    - the mechanism hasn't actually moved, only the coordinate labels
    have. X's MIN_DEG/MAX_DEG are in degrees; Y/Z's MIN_MM/MAX_MM are in
    millimeters (via LEAD). Used by both HOME (zeroes at the stall point,
    Y/Z only) and the standalone ZERO command (zeroes wherever the axis
    is right now, X/Y/Z). Safe to call while the axis is running: it only
    touches state dict entries, no motor I/O, and (uasyncio being
    cooperative) nothing else runs until this function returns, so
    bounce_task/x_task can't observe a half-shifted state.
    """
    st = state[state_key]
    offset = st["pos"]
    st["pos"] = 0
    if "min_deg" in st:
        offset_deg = offset * 360.0 / steps_per_rev(state_key)
        st["min_deg"] -= offset_deg
        st["max_deg"] -= offset_deg
    if "min_mm" in st:
        offset_mm = offset / (steps_per_rev(state_key) / st["lead_mm"])
        st["min_mm"] -= offset_mm
        st["max_mm"] -= offset_mm


def set_axis_microsteps(state_key, motor, new_microsteps):
    """Changes the driver's microstep resolution and rescales "pos" by the
    ratio, so it keeps meaning the same real physical location - a single
    step means a different real distance at a different microstep
    setting. MIN/MAX don't need this: they're kept in physical units
    (degrees for X, millimeters for Y/Z), not steps - see the state dict
    comment. Writes to the driver first: if new_microsteps isn't a valid
    setting, TMC2209.set_microsteps() raises ValueError before any state
    changes.
    """
    st = state[state_key]
    old_microsteps = st["microsteps"]
    motor.set_microsteps(new_microsteps)
    if new_microsteps != old_microsteps:
        st["pos"] = round(st["pos"] * new_microsteps / old_microsteps)
    st["microsteps"] = new_microsteps


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
    run_current_ma = st["current_ma"]
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
                    stall_mm = st["pos"] / (steps_per_rev(state_key) / st["lead_mm"])
                    if direction > 0:
                        st["max_mm"] = stall_mm
                    else:
                        st["min_mm"] = stall_mm
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
    steps via the axis's LEAD (mm/screw-revolution) and its own configured
    microsteps/rev (see steps_per_rev). Like HOME, requires the axis not
    already bouncing. Clamps the target to MIN/MAX so it can't grind past
    a homed limit.
    """
    st = state[state_key]
    if st["running"]:
        print(state_key.upper(), "MOVE: stop the axis first")
        return

    steps_per_mm = steps_per_rev(state_key) / st["lead_mm"]
    target_pos = st["pos"] + round(distance_mm * steps_per_mm)
    min_pos = round(st["min_mm"] * steps_per_mm)
    max_pos = round(st["max_mm"] * steps_per_mm)
    clamped_pos = max(min_pos, min(max_pos, target_pos))
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


PSEUDO_POSITIONS = ("MIN", "MAX", "MID")


async def move_linear_axis_to(motor, state_key, pseudo):
    """One-shot absolute move of Y/Z to a named pseudo-position: MIN, MAX,
    or MID (the midpoint between them) - see PSEUDO_POSITIONS. Unlike
    move_linear_axis's signed relative distance in mm, this goes straight
    to that position from wherever the axis currently is. Requires the
    axis not already bouncing.
    """
    st = state[state_key]
    if st["running"]:
        print(state_key.upper(), "MOVE: stop the axis first")
        return

    if pseudo == "MIN":
        target_mm = st["min_mm"]
    elif pseudo == "MAX":
        target_mm = st["max_mm"]
    else:
        target_mm = (st["min_mm"] + st["max_mm"]) / 2.0
    target_pos = round(target_mm * steps_per_rev(state_key) / st["lead_mm"])

    steps = abs(target_pos - st["pos"])
    if steps == 0:
        print(state_key.upper(), "MOVE: already at", pseudo)
        return
    direction = 1 if target_pos > st["pos"] else -1

    speed = max(1, abs(st["speed"]))
    period_ms = max(1, int(1000 / speed))
    motor.dir.value(1 if direction > 0 else 0)
    for _ in range(steps):
        motor.step.value(1)
        time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
        motor.step.value(0)
        await asyncio.sleep_ms(period_ms)
        st["pos"] += direction
    print(state_key.upper(), "moved to", pseudo, "(%d steps), pos=%d" % (steps, st["pos"]))


async def rotate_x(degrees):
    """One-shot relative rotation of X by degrees (signed), converted to
    steps via X's own configured microsteps/rev (see steps_per_rev). NOT
    clamped to MIN_DEG/MAX_DEG - unlike Y/Z MOVE, a plain numeric X MOVE
    is deliberately unbounded, since X is continuous rotation and
    multi-revolution moves (e.g. "X MOVE 720" for two full turns) are a
    legitimate use case; MIN_DEG/MAX_DEG only matter for the MIN/MAX/MID
    pseudo-positions (see rotate_x_to). Requires the axis not already
    running.
    """
    st = state["x"]
    if st["running"]:
        print("X MOVE: stop the axis first")
        return

    steps = round(abs(degrees) * steps_per_rev("x") / 360.0)
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


async def rotate_x_to(pseudo):
    """One-shot absolute rotation of X to a named pseudo-position: MIN,
    MAX, or MID (the midpoint between them) - see PSEUDO_POSITIONS, in
    degrees (MIN_DEG/MAX_DEG). Unlike rotate_x's signed relative angle,
    this goes straight to that angle from wherever the axis currently is.
    Requires the axis not already running.
    """
    st = state["x"]
    if st["running"]:
        print("X MOVE: stop the axis first")
        return

    if pseudo == "MIN":
        target_deg = st["min_deg"]
    elif pseudo == "MAX":
        target_deg = st["max_deg"]
    else:
        target_deg = (st["min_deg"] + st["max_deg"]) / 2.0
    target_pos = round(target_deg * steps_per_rev("x") / 360.0)

    steps = abs(target_pos - st["pos"])
    if steps == 0:
        print("X MOVE: already at", pseudo)
        return
    direction = 1 if target_pos > st["pos"] else -1

    speed = max(1, abs(st["speed"]) or 200)
    period_ms = max(1, int(1000 / speed))
    x_motor.dir.value(1 if direction > 0 else 0)
    for _ in range(steps):
        x_motor.step.value(1)
        time.sleep_us(3)  # minimum STEP pulse width - brief enough not to matter
        x_motor.step.value(0)
        await asyncio.sleep_ms(period_ms)
        st["pos"] += direction
    print("X moved to", pseudo, "(%d steps), pos=%d" % (steps, st["pos"]))


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


def move_servo_to(pseudo):
    """One-shot absolute move of A to a named pseudo-position: MIN, MAX, or
    MID (the midpoint between them) - see PSEUDO_POSITIONS. Unlike
    move_servo's relative delta, the target doesn't depend on the current
    position, so there's no need to read it back first. Requires the axis
    not already bouncing.
    """
    st = state["a"]
    if st["running"]:
        print("A MOVE: stop the axis first")
        return

    if pseudo == "MIN":
        target_deg = st["min_deg"]
    elif pseudo == "MAX":
        target_deg = st["max_deg"]
    else:
        target_deg = (st["min_deg"] + st["max_deg"]) / 2.0
    servo.set_goal_deg(target_deg, speed=st["speed"])
    print("A moving to", pseudo, "(%.4g deg)" % target_deg)


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


# ---------------- sleep/wake ----------------

SLEEP_TIMEOUT_S = 20 * 60  # auto-SLEEP after this long with nothing running and no
                            # console input at all - see sleep_monitor_task
SLEEP_CHECK_INTERVAL_S = 30  # how often sleep_monitor_task checks the idle timer
SLEEP_SERVO_RESTORE_TOLERANCE_DEG = 1.0  # ignore a post-wake position difference this
                                          # small - sensor noise, not real sag

_sleeping = False
_pre_sleep_servo_deg = None  # A's angle just before SLEEP, so WAKE can detect sag and
                              # correct it - see enter_sleep/wake_up
_last_activity_ms = None  # set on every console command - see _dispatch_command


def enter_sleep():
    """Disables the X/Y/Z drivers (EN pin high - no holding current at all,
    unlike the normal IHOLD current-scale-down) and releases the servo's
    torque, to cut power/heat during a long idle stretch. Does NOT stop
    any axis first - callers that want a clean stop (the SLEEP command)
    should call stop_all() first; the auto-sleep monitor only ever fires
    when everything's already stopped, so it doesn't need to.
    """
    global _sleeping, _pre_sleep_servo_deg
    if _sleeping:
        return
    for m in (x_motor, y_motor, z_motor):
        m.enable_driver(False)
    try:
        _pre_sleep_servo_deg = servo.read_position_deg()
    except OSError:
        _pre_sleep_servo_deg = None  # can't check for sag on wake, but sleep anyway
    servo.torque_enable(False)
    _sleeping = True
    print("ok SLEEP - X/Y/Z drivers disabled, servo torque released")


def wake_up():
    """Re-enables the X/Y/Z drivers and the servo's torque. Because a
    torque-less servo can sag under the weight of whatever it's holding
    (see the module's SLEEP docs), this also checks the servo's current
    position against what it was right before SLEEP and, if it moved by
    more than SLEEP_SERVO_RESTORE_TOLERANCE_DEG, commands it back - the
    whole reason enter_sleep() bothers recording _pre_sleep_servo_deg.
    """
    global _sleeping, _pre_sleep_servo_deg
    if not _sleeping:
        return
    for m in (x_motor, y_motor, z_motor):
        m.enable_driver(True)
    servo.torque_enable(True)
    if _pre_sleep_servo_deg is not None:
        try:
            current_deg = servo.read_position_deg()
            if abs(current_deg - _pre_sleep_servo_deg) > SLEEP_SERVO_RESTORE_TOLERANCE_DEG:
                servo.set_goal_deg(_pre_sleep_servo_deg, speed=state["a"]["speed"])
                print("A: sagged to %.4g deg while asleep, restoring to %.4g deg" %
                      (current_deg, _pre_sleep_servo_deg))
        except OSError:
            pass  # can't verify - leave it wherever it is rather than guess
    _sleeping = False
    _pre_sleep_servo_deg = None
    print("ok WAKE - X/Y/Z drivers and servo torque re-enabled")


async def sleep_monitor_task():
    global _last_activity_ms
    _last_activity_ms = time.ticks_ms()
    while True:
        await asyncio.sleep(SLEEP_CHECK_INTERVAL_S)
        if _sleeping:
            continue
        if any(state[key]["running"] for key in ("x", "y", "z", "a")):
            continue  # something's actively moving - that's not "idle", however
                       # stale _last_activity_ms is (see _dispatch_command)
        if time.ticks_diff(time.ticks_ms(), _last_activity_ms) >= SLEEP_TIMEOUT_S * 1000:
            enter_sleep()


# ---------------- console ----------------

def print_status():
    print("SLEEP:", "yes (X/Y/Z drivers disabled, servo torque released)" if _sleeping else "no")
    x, y, z, a = state["x"], state["y"], state["z"], state["a"]
    print("X running=%s speed=%d dir=%s pos=%d (%.4gdeg) min_deg=%.4g max_deg=%.4g "
          "microsteps=%d current_ma=%d" %
          (x["running"], x["speed"], "CW" if x["speed"] >= 0 else "CCW",
           x["pos"], x["pos"] * 360.0 / steps_per_rev("x"), x["min_deg"], x["max_deg"],
           x["microsteps"], x["current_ma"]))
    print("Y running=%s speed=%d pos=%d (%.4gmm) min_mm=%.4g max_mm=%.4g sgthrs=%d "
          "lead_mm=%.4g microsteps=%d current_ma=%d" %
          (y["running"], y["speed"], y["pos"], y["pos"] * y["lead_mm"] / steps_per_rev("y"),
           y["min_mm"], y["max_mm"], y["sgthrs"], y["lead_mm"],
           y["microsteps"], y["current_ma"]))
    print("Z running=%s speed=%d pos=%d (%.4gmm) min_mm=%.4g max_mm=%.4g sgthrs=%d "
          "lead_mm=%.4g microsteps=%d current_ma=%d" %
          (z["running"], z["speed"], z["pos"], z["pos"] * z["lead_mm"] / steps_per_rev("z"),
           z["min_mm"], z["max_mm"], z["sgthrs"], z["lead_mm"],
           z["microsteps"], z["current_ma"]))
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
    global _last_activity_ms
    parts = line.strip().split()
    if not parts:
        return
    _last_activity_ms = time.ticks_ms()  # any input counts, not just movement - see
                                          # sleep_monitor_task/SLEEP_TIMEOUT_S
    cmd = parts[0].upper()

    if cmd == "STATUS":
        print_status()
        return
    if cmd == "HELP":
        print(HELP_TEXT)
        return
    if cmd == "SLEEP":
        stop_all()
        enter_sleep()
        return
    if cmd == "WAKE":
        wake_up()
        return
    if cmd == "START":
        if _sleeping:
            wake_up()
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

    if _sleeping and sub in ("START", "MOVE", "HOME"):
        wake_up()

    if len(parts) == 2 and sub in _QUERYABLE_FIELDS and cmd in _QUERYABLE_FIELDS[sub]:
        field = _QUERYABLE_FIELDS[sub][cmd]
        print("%s %s = %s" % (cmd, sub, axis[field]))
        return

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
        elif sub == "MICROSTEPS" and len(parts) >= 3 and cmd in ("X", "Y", "Z"):
            motor = {"X": x_motor, "Y": y_motor, "Z": z_motor}[cmd]
            set_axis_microsteps(cmd.lower(), motor, int(parts[2]))
            persist = True
        elif sub == "CURRENT" and len(parts) >= 3 and cmd in ("X", "Y", "Z"):
            motor = {"X": x_motor, "Y": y_motor, "Z": z_motor}[cmd]
            axis["current_ma"] = int(parts[2])
            motor.set_current(axis["current_ma"])
            persist = True
        elif sub == "TMC" and cmd in ("X", "Y", "Z"):
            motor = {"X": x_motor, "Y": y_motor, "Z": z_motor}[cmd]
            print(cmd, "TMC:", motor.diag_summary(axis.get("sgthrs")))
        elif sub == "TMC" and cmd == "A":
            print("A TMC:", servo.diag_summary())
        elif sub == "SPEED" and len(parts) >= 3:
            axis["speed"] = int(parts[2])
            persist = True
        elif sub == "MIN" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["min_mm"] = float(parts[2])
            persist = True
        elif sub == "MAX" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["max_mm"] = float(parts[2])
            persist = True
        elif sub == "SGTHRS" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["sgthrs"] = int(parts[2])
            persist = True
        elif sub == "LEAD" and len(parts) >= 3 and cmd in ("Y", "Z"):
            axis["lead_mm"] = float(parts[2])
            persist = True
        elif sub == "MOVE" and len(parts) >= 3 and cmd in ("Y", "Z"):
            motor = y_motor if cmd == "Y" else z_motor
            target = parts[2].upper()
            if target in PSEUDO_POSITIONS:
                asyncio.create_task(move_linear_axis_to(motor, cmd.lower(), target))
            else:
                asyncio.create_task(move_linear_axis(motor, cmd.lower(), float(parts[2])))
        elif sub == "MOVE" and len(parts) >= 3 and cmd == "X":
            target = parts[2].upper()
            if target in PSEUDO_POSITIONS:
                asyncio.create_task(rotate_x_to(target))
            else:
                asyncio.create_task(rotate_x(float(parts[2])))
        elif sub == "MOVE" and len(parts) >= 3 and cmd == "A":
            target = parts[2].upper()
            if target in PSEUDO_POSITIONS:
                move_servo_to(target)
            else:
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
        elif sub == "MIN" and len(parts) >= 3 and cmd in ("X", "A"):
            axis["min_deg"] = float(parts[2])
            persist = True
        elif sub == "MAX" and len(parts) >= 3 and cmd in ("X", "A"):
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
                          servo_task(), console_task(), position_autosave_task(),
                          sleep_monitor_task())


if __name__ == "__main__":
    asyncio.run(main())
