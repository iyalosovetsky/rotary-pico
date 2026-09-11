# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MicroPython firmware for a BTT SKR Pico (RP2040) controlling a DIY turntable rig for a Creality Raptor-style 3D scanner: X axis rotates the table continuously, Y axis bounces a scanner carriage between two limits, and an ST3215 serial bus servo bounces the scanner's tilt angle between two limits. All three run concurrently via `uasyncio`, driven by a G-code-like console command language. See `README.md` for the full command reference and hardware photos/docs links.

There is no build/lint/test tooling in this repo — it's plain MicroPython source, deployed by copying files to the board (Thonny, or `mpremote fs cp <file> :`) and run directly on-device.

## Architecture

**Two independent serial buses, two different wire protocols, one shared address-and-pin convention:**

- `tmc2209.py` — driver for the 4 onboard TMC2209 stepper driver chips. They all share **one physical UART bus** (SKR Pico wiring: TX=gpio8 through a 1k resistor, RX=gpio9 tied directly to PDN_UART), distinguished by a per-driver node address (0-3, set by each chip's MS1/MS2 strapping — matches `uart_address` in the machine's old Klipper `printer.cfg`, which is where the STEP/DIR/EN pin numbers and addresses hardcoded in `scanner_rig.py`/`main.py` came from). Because TX and RX are the same physical wire, every byte the host sends echoes back on RX and must be drained before reading a real reply — both `TMC2209Bus.write_register` and `read_register` do this; don't remove those drains when touching this file.
- `st3215.py` — driver for the ST3215 servo, a completely separate protocol (Feetech SMS/STS, packet-based with a CRC-less checksum: `~(id+len+inst+params) & 0xFF`) over a second UART, wired through a Waveshare Bus Servo Adapter (A) (needed because this bus is single-wire half-duplex at the hardware level, unlike the TMC2209 trick above which works with a bare resistor). Register map and instruction opcodes in this file were verified against the official `parallax/scservo` and `ftservo/FTServo_Python` SDKs — if you need to add a register, look it up there rather than guessing.
- `scanner_rig.py` — the actual controller. Holds a `state` dict per axis (`x`, `y`, `s`) mutated by the console parser and read by three independent `asyncio` tasks (`x_task`, `y_task`, `servo_task`) plus a non-blocking stdin reader (`console_task`, using `select.poll` on `sys.stdin` since MicroPython's stdin read is otherwise blocking). Motion is intentionally simple/blocking-per-step inside each task (`Pin.value()` toggling with `asyncio.sleep_us`) rather than PIO — fine at these speeds, but a place to look first if step timing ever needs to go faster/smoother.
- `main.py` — a minimal single-axis bring-up/diagnostic script (not the full rig), useful for testing a fresh board or a wiring change in isolation before running the full `scanner_rig.py`.

**Current calculation** (`TMC2209.set_current`) implements the standard Trinamic formula `CS = 32*sqrt(2)*I_rms*(Rsense+0.02)/Vfs - 1`; `Rsense`/`vsense` are constructor args, not hardcoded, if a different driver current-sense config is ever used.

**Position tracking is open-loop everywhere** — no endstops/homing in this codebase. Y's `pos` in `scanner_rig.py` is just a step counter from wherever the board was powered on; `MIN`/`MAX` are relative to that, not to any physical reference.
