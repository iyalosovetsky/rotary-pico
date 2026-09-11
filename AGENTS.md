# AGENTS.md

Guidance for agents working in this repo. Read `CLAUDE.md` too — it documents
the architecture (bus protocols, task layout, current-calc formula, open-loop
positioning) in detail; this file covers workflow/process facts CLAUDE.md
doesn't.

## What this is

MicroPython firmware for a BTT SKR Pico (RP2040) driving a DIY 3D-scanner
turntable rig. No build system, no package manager, no tests — plain
MicroPython source files deployed straight to the board.

## Deployment (no build/test tooling exists)

- Deploy by copying files to the board: Thonny, or `mpremote fs cp <file> :`.
- There is nothing to run locally to "build" or "test" this — verification
  only happens by copying to real hardware and observing behavior over the
  console/REPL. Don't invent lint/test commands; none exist.
- `main.py` is a minimal single-axis bench-test script for bring-up/wiring
  checks — it is not the full rig and is not run alongside `scanner_rig.py`.
  `scanner_rig.py` is the actual controller, run standalone on the board.

## Code layout

| File | Role |
|---|---|
| `tmc2209.py` | Driver for the 4 onboard TMC2209 stepper chips (shared UART bus) |
| `st3215.py` | Driver for the ST3215 serial bus servo (Feetech SMS/STS protocol) |
| `scanner_rig.py` | Orchestrator: per-axis `state` dict + async X/Y/servo tasks + console parser |
| `main.py` | Single-axis bring-up/diagnostic bench test, not the full rig |
| `freecad/` | FreeCAD models (stepper motor mount, servo mount) |
| `table_models/` | Third-party turntable STEP models + parts list, not this project's own designs |

## Hardware/wiring facts that are easy to get wrong

- Two completely separate UART buses at different baud rates, both hardcoded
  in `scanner_rig.py`/`main.py`:
  - `TMC2209Bus(uart_id=1, tx=8, rx=9, baudrate=40000)` — shared bus for all
    4 stepper drivers, addressed 0-3 via MS1/MS2 strapping.
  - `ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)` — the ST3215 servo,
    wired through the **Laser** connector (IO0/IO1) via a Waveshare Bus Servo
    Adapter (A), *not* the board's `SERVOS` connector (IO29 is a single PWM
    pin and can't carry the servo's 2-wire UART protocol).
- Full pin/connector map, including which SKR Pico connectors are still free
  for expansion, is in `PINOUT.md` (and `PINOUT.uk.md`, its Ukrainian twin).
- There is no homing/endstops anywhere in this codebase — all positions
  (`Y`'s step counter, servo angle) are relative to wherever the board
  happened to power on, not to a physical reference. Don't assume `MIN`/`MAX`
  values mean anything absolute.

## Docs conventions

- `README.md`/`PINOUT.md` are the English source of truth; `README.uk.md`/
  `PINOUT.uk.md` are Ukrainian translations kept in sync manually — if you
  edit one language's version of either doc, update the other to match.
- `README.md` has the full console command reference (`X SPEED`, `Y MIN/MAX`,
  `S MIN/MAX`, `STATUS`, `HELP`, etc.) — check it before assuming a command's
  syntax rather than reading `scanner_rig.py`'s parser from scratch.
