"""Bench test: TMC2209 drivers on BTT SKR Pico, controlled from the console.

Pins/addresses below are taken directly from this board's printer.cfg.
"""

from tmc2209 import TMC2209Bus, TMC2209, ADDR_X, ADDR_Y, ADDR_Z, ADDR_E

bus = TMC2209Bus(uart_id=1, tx=8, rx=9, baudrate=40000)

motors = {
    "x": TMC2209(bus, ADDR_X, step_pin=11, dir_pin=10, en_pin=12),
    "y": TMC2209(bus, ADDR_Y, step_pin=6, dir_pin=5, en_pin=7),
    "z": TMC2209(bus, ADDR_Z, step_pin=19, dir_pin=28, en_pin=2),
    "e": TMC2209(bus, ADDR_E, step_pin=14, dir_pin=13, en_pin=15),
}

RUN_CURRENT_MA = 500  # start conservative, raise once you confirm the motor stays cool


def setup():
    for name, m in motors.items():
        m.check_connection()
        print(name, "connected, IOIN version OK")
        m.enable_uart_mode(spreadcycle=False)
        m.set_current(RUN_CURRENT_MA)
        m.set_microsteps(16)
        m.enable_driver(True)
    print("all drivers ready")


def repl():
    print("commands: <axis> <steps> [delay_us]   e.g.  x 200   or   y -400 600")
    print("          off <axis>   -  disable driver")
    while True:
        try:
            line = input("> ").strip().split()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line[0] == "off" and len(line) > 1 and line[1] in motors:
            motors[line[1]].enable_driver(False)
            print(line[1], "disabled")
            continue
        if line[0] in motors and len(line) >= 2:
            axis = line[0]
            steps = int(line[1])
            delay = int(line[2]) if len(line) > 2 else 800
            motors[axis].move(steps, delay)
            print(axis, "moved", steps, "steps")
            continue
        print("unrecognised command:", line)


if __name__ == "__main__":
    setup()
    repl()
