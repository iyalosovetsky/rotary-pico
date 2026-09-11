"""Turntable + line-scan + tilt-servo controller for the DIY Creality
Raptor-style 3D scanner rig.

  X = turntable (continuous rotation)
  Y = scanner carriage (bounces between two limits over the table)
  S = ST3215 servo tilting the scanner head (bounces between two angles)

Console commands (G-code-like, one per line):

    X SPEED <steps_per_sec>     signed: sign sets direction, 0 = stopped
    X START
    X STOP

    Y MIN <steps>
    Y MAX <steps>
    Y SPEED <steps_per_sec>     unsigned
    Y START
    Y STOP

    S MIN <deg>
    S MAX <deg>
    S SPEED <raw_units>         servo-internal speed register, try 0-1000
    S START
    S STOP

    STATUS
    HELP

Rename this file to main.py once you're happy with it, to have it run
on boot. Left as scanner_rig.py for now so it doesn't clobber the
existing bench-test main.py.
"""

import sys
import select
import uasyncio as asyncio

from tmc2209 import TMC2209Bus, TMC2209, ADDR_X, ADDR_Y
from st3215 import ServoBus, ST3215

# ---- stepper bus + motors (pins/addresses from printer.cfg) ----
stepper_bus = TMC2209Bus(uart_id=1, tx=8, rx=9, baudrate=40000)
x_motor = TMC2209(stepper_bus, ADDR_X, step_pin=11, dir_pin=10, en_pin=12)
y_motor = TMC2209(stepper_bus, ADDR_Y, step_pin=6, dir_pin=5, en_pin=7)

# ---- servo bus (CHANGE tx/rx to match your actual wiring/adapter!) ----
servo_bus = ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)
servo = ST3215(servo_bus, servo_id=1)

X_CURRENT_MA = 500
Y_CURRENT_MA = 500

state = {
    "x": {"running": False, "speed": 200},
    "y": {"running": False, "speed": 400, "min": 0, "max": 3200, "pos": 0, "dir": 1},
    "s": {"running": False, "speed": 300, "min_deg": 30, "max_deg": 150},
}


def setup_motors():
    for m, current in ((x_motor, X_CURRENT_MA), (y_motor, Y_CURRENT_MA)):
        m.check_connection()
        m.enable_uart_mode(spreadcycle=False)
        m.set_current(current)
        m.set_microsteps(16)
        m.enable_driver(True)
    print("X/Y drivers ready")

    if servo.ping():
        servo.torque_enable(True)
        print("servo ready")
    else:
        print("WARNING: servo did not respond to ping - check wiring/id, S commands will fail")


# ---------------- motion tasks ----------------

async def x_task():
    while True:
        st = state["x"]
        if st["running"] and st["speed"] != 0:
            x_motor.dir.value(1 if st["speed"] > 0 else 0)
            half_us = max(50, int(500000 / abs(st["speed"])))
            x_motor.step.value(1)
            await asyncio.sleep_us(half_us)
            x_motor.step.value(0)
            await asyncio.sleep_us(half_us)
        else:
            await asyncio.sleep_ms(20)


async def y_task():
    while True:
        st = state["y"]
        if st["running"]:
            target = st["max"] if st["dir"] == 1 else st["min"]
            if st["pos"] == target:
                st["dir"] *= -1
                target = st["max"] if st["dir"] == 1 else st["min"]
            step_dir = 1 if target > st["pos"] else -1
            y_motor.dir.value(1 if step_dir > 0 else 0)
            half_us = max(50, int(500000 / max(1, st["speed"])))
            y_motor.step.value(1)
            await asyncio.sleep_us(half_us)
            y_motor.step.value(0)
            await asyncio.sleep_us(half_us)
            st["pos"] += step_dir
        else:
            await asyncio.sleep_ms(20)


async def servo_task():
    going_to_max = True
    while True:
        st = state["s"]
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
    x, y, s = state["x"], state["y"], state["s"]
    print("X running=%s speed=%d" % (x["running"], x["speed"]))
    print("Y running=%s speed=%d min=%d max=%d pos=%d" %
          (y["running"], y["speed"], y["min"], y["max"], y["pos"]))
    print("S running=%s speed=%d min_deg=%d max_deg=%d" %
          (s["running"], s["speed"], s["min_deg"], s["max_deg"]))


def handle_command(line):
    parts = line.strip().split()
    if not parts:
        return
    cmd = parts[0].upper()

    if cmd == "STATUS":
        print_status()
        return
    if cmd == "HELP":
        print(__doc__)
        return

    if cmd not in ("X", "Y", "S") or len(parts) < 2:
        print("? unrecognised command:", line)
        return

    sub = parts[1].upper()
    axis = {"X": state["x"], "Y": state["y"], "S": state["s"]}[cmd]

    try:
        if sub == "START":
            axis["running"] = True
        elif sub == "STOP":
            axis["running"] = False
        elif sub == "SPEED" and len(parts) >= 3:
            axis["speed"] = int(parts[2])
        elif sub == "MIN" and len(parts) >= 3 and cmd == "Y":
            axis["min"] = int(parts[2])
        elif sub == "MAX" and len(parts) >= 3 and cmd == "Y":
            axis["max"] = int(parts[2])
        elif sub == "MIN" and len(parts) >= 3 and cmd == "S":
            axis["min_deg"] = float(parts[2])
        elif sub == "MAX" and len(parts) >= 3 and cmd == "S":
            axis["max_deg"] = float(parts[2])
        else:
            print("? unrecognised command:", line)
            return
    except ValueError:
        print("? bad numeric value:", line)
        return

    print("ok", line)


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
    await asyncio.gather(x_task(), y_task(), servo_task(), console_task())


if __name__ == "__main__":
    asyncio.run(main())
