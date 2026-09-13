"""Bench test: sweep Y-axis microstepping x speed combinations on the TMC2209.

For every microstep setting in MICROSTEPS, drives the Y motor for
TEST_SECONDS at each of three step rates (max/half/min from SPEEDS),
then immediately drives the same number of steps back the other way
before moving to the next combination - net displacement per
combination is ~0, but each forward leg alone moves (speed * TEST_SECONDS)
microsteps in one direction, so make sure the carriage has clearance
before running this on a mounted axis.

Not part of scanner_rig.py - a standalone diagnostic, same spirit as
main.py's bench REPL. Run directly via Thonny or `mpremote run`.
"""

import time
from tmc2209 import TMC2209Bus, TMC2209, ADDR_Y

TEST_CURRENT_MA = 600  # conservative bench current - raise once you've confirmed the motor stays cool
TEST_SECONDS = 5

MICROSTEPS = [256, 128, 64, 32, 16, 8, 4, 2, 1]  # full TMC2209 microstep table, coarsest last

MAX_SPEED = 4000  # steps/sec - fast bench-test rate
HALF_SPEED = MAX_SPEED // 2
MIN_SPEED = 100  # steps/sec - slow crawl
SPEEDS = [("max", MAX_SPEED), ("half", HALF_SPEED), ("min", MIN_SPEED)]

bus = TMC2209Bus(uart_id=1, tx=8, rx=9, baudrate=40000)
y_motor = TMC2209(bus, ADDR_Y, step_pin=6, dir_pin=5, en_pin=7)


def setup():
    y_motor.check_connection()
    y_motor.enable_uart_mode(spreadcycle=False)
    y_motor.set_current(TEST_CURRENT_MA)
    y_motor.enable_driver(True)
    print("Y driver ready, current=%dmA" % TEST_CURRENT_MA)


def step_n(n, speed, forward):
    """Issues exactly n STEP pulses at the given rate."""
    y_motor.dir.value(1 if forward else 0)
    time.sleep_us(5)  # DIR setup time before the first STEP edge
    half_period_us = max(1, int(1_000_000 / speed / 2))
    for _ in range(n):
        y_motor.step.value(1)
        time.sleep_us(half_period_us)
        y_motor.step.value(0)
        time.sleep_us(half_period_us)


def run_for(seconds, speed, forward):
    """Steps at a fixed rate for `seconds`, returns the step count actually issued."""
    y_motor.dir.value(1 if forward else 0)
    time.sleep_us(5)  # DIR setup time before the first STEP edge
    half_period_us = max(1, int(1_000_000 / speed / 2))
    deadline = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    steps = 0
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        y_motor.step.value(1)
        time.sleep_us(half_period_us)
        y_motor.step.value(0)
        time.sleep_us(half_period_us)
        steps += 1
    return steps


def run_test():
    setup()
    for microsteps in MICROSTEPS:
        y_motor.set_microsteps(microsteps)
        print("\n== microsteps=%d ==" % microsteps)
        for label, speed in SPEEDS:
            print("  %s speed (%d steps/sec): forward %ds..." % (label, speed, TEST_SECONDS))
            steps = run_for(TEST_SECONDS, speed, forward=True)
            print("  %s speed: back %d steps..." % (label, steps))
            if steps:
                step_n(steps, speed, forward=False)
            print("  %s speed done (%d steps issued)" % (label, steps))
    y_motor.enable_driver(False)
    print("\nsweep complete, driver disabled")


if __name__ == "__main__":
    run_test()
