*[Українська версія](README.uk.md)*

# rotary-pico

## 1. Description

Control firmware for a DIY turntable rig for a Creality Raptor-style 3D scanner, built on a **BTT SKR Pico** board (RP2040, MicroPython).

- **X axis** — rotates the table (continuous rotation, speed control), plus a one-shot relative rotation to a given angle.
- **Y/Z axes** — cyclic motion between a lower and upper limit, no physical endstops: `HOME` drives the axis until the TMC2209's StallGuard (sensorless homing) detects a genuine stall, then sets `MIN`/`MAX` to that position — a one-shot calibration, not something re-checked on every bounce. Also support a one-shot relative move to a given distance in millimeters, via a configurable lead screw pitch.
- **ST3215 servo (A)** — tilts the scanner head (cyclic motion between a minimum and maximum angle), plus a one-shot relative move to a given angle using the servo's own position feedback.

X/Y/Z track their current position (an open-loop step count, since none of them has a position sensor) and persist it so it survives a reboot; A doesn't need this since the servo always reports its own true position. `STATUS` shows every axis's position in physical units (mm/degrees).

All axes run concurrently and independently of each other (cooperative multitasking via `uasyncio`), controlled through G-code-like console commands.

The project was inspired by the [Creality Raptor Turntable](https://www.youtube.com/watch?v=kjL7HI78B2U&t=881s) video — `table_models/` contains the turntable models from the same author.

### Project files

| File / folder | Purpose |
|---|---|
| `tmc2209.py` | TMC2209 driver over UART (shared bus, MS1/MS2 addressing) |
| `st3215.py` | ST3215 servo driver (Feetech SMS/STS protocol) |
| `scanner_rig.py` | Orchestrator: async X/Y/Z/servo tasks + console command parser |
| `main.py` | Simple single-motor bench test (bring-up/diagnostics) |
| `test_y_motor.py` | Bench sweep: every microstep setting x three speeds, for characterizing real step rate vs. requested |
| `freecad/` | Own FreeCAD models (stepper motor, servo mount) |
| `table_models/` | Turntable models (STEP) from the inspiring video's author |

### Documentation

- [TMC2209_REGISTERS.md](TMC2209_REGISTERS.md) - every TMC2209 register this codebase uses, bit layouts, and a link to the datasheet
- [ST3215_REGISTERS.md](ST3215_REGISTERS.md) - every ST3215 register this codebase uses, units/scaling, and links to the datasheet
- [PINOUT.md](PINOUT.md) - BTT SKR Pico pin/header reference for this rig's wiring
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - debugging log: bugs found, dead ends ruled out, current open issues

## 2. Command reference

Commands are sent one per line over the console (REPL):

| Command | Description |
|---|---|
| `START [minutes]` | Start every axis at once (using whatever they're each already configured with), auto-stop after `minutes` (default 5) |
| `STOP` | Stop every axis immediately |
| `X SPEED <steps_per_sec>` | Table rotation speed (sign sets direction, 0 = stopped) |
| `X START [CW\|CCW]` | Start table rotation - direction optional, defaults to CW (or last-used) |
| `X STOP` | Stop table rotation |
| `X MOVE <deg>` | One-shot relative rotation by a signed angle - axis must be stopped first |
| `Y MIN <steps>` | Lower limit of carriage travel (microsteps) |
| `Y MAX <steps>` | Upper limit of carriage travel (microsteps) |
| `Y SPEED <steps_per_sec>` | Carriage speed |
| `Y SGTHRS <0-255>` | StallGuard sensorless-homing threshold (see below) - higher trips more easily |
| `Y HOME [DEC\|INC] [speed]` | One-shot calibration: home toward a StallGuard stall (see below) |
| `Y LEAD <mm>` | Lead screw pitch (mm per screw revolution) - used to convert `MOVE`'s millimeters to steps |
| `Y MOVE <mm>` | One-shot relative move by a signed distance in mm - axis must be stopped first, clamped to `MIN`/`MAX` |
| `Y START` | Start cyclic motion between `MIN` and `MAX` |
| `Y STOP` | Stop the carriage |
| `Z MIN <steps>` | Lower limit of Z travel (microsteps) |
| `Z MAX <steps>` | Upper limit of Z travel (microsteps) |
| `Z SPEED <steps_per_sec>` | Z axis speed |
| `Z SGTHRS <0-255>` | StallGuard sensorless-homing threshold (see below) - higher trips more easily |
| `Z HOME [DEC\|INC] [speed]` | One-shot calibration: home toward a StallGuard stall (see below) |
| `Z LEAD <mm>` | Lead screw pitch (mm per screw revolution) - used to convert `MOVE`'s millimeters to steps |
| `Z MOVE <mm>` | One-shot relative move by a signed distance in mm - axis must be stopped first, clamped to `MIN`/`MAX` |
| `Z START` | Start cyclic motion between `MIN` and `MAX` |
| `Z STOP` | Stop the Z axis |
| `A MIN <deg>` | Minimum scanner tilt angle (degrees) |
| `A MAX <deg>` | Maximum scanner tilt angle (degrees) |
| `A SPEED <raw_units>` | Servo speed (raw register units, tune empirically) |
| `A MOVE <deg>` | One-shot relative move by a signed angle - axis must be stopped first, clamped to `MIN`/`MAX` |
| `A START` | Start cyclic tilt between `MIN` and `MAX` |
| `A STOP` | Stop the servo |
| `STATUS` | Current position and config of all four axes (X/Y/Z in steps + degrees/mm, A read live from the servo) |
| `HELP` | Command help |

Example session:

```
Y HOME
Z HOME
X SPEED 200
X START
Y SPEED 400
Y START
Z SPEED 400
Z START
A MIN 30
A MAX 150
A SPEED 300
A START
STATUS
```

Or, for one-shot positioning instead of continuous cycling:

```
Y HOME
Y LEAD 4
Y MOVE 25.5
X MOVE 90
A MOVE -15
STATUS
```

### Y/Z sensorless homing (StallGuard)

Y and Z have no physical endstop switches. Instead, `HOME` deliberately drives the axis toward one end (`DEC` = decreasing position, `INC` = increasing; Y defaults to `DEC`, Z to `INC`) while polling the TMC2209's StallGuard result (`SG_RESULT`) over UART - it drops as motor load rises, so driving into a real mechanical stop reads as a stall. Once that happens, `MIN` (for a `DEC` stall) or `MAX` (for an `INC` stall) is set to the position it stalled at.

This is a one-shot calibration - run `HOME` once before the first `START`, the way Klipper/Voron-style sensorless homing works. Ordinary bouncing afterward does **not** re-check StallGuard on every move: it runs the quieter stealthChop mode at full current, under which the StallGuard signal isn't reliable enough to act on. `HOME` switches to spreadCycle and a reduced current just for the homing move, then restores normal settings afterward.

`SGTHRS` has no universal default - it's specific to your motor, current, speed and mechanics, and must be tuned by hand:

1. Set a low `SGTHRS` (e.g. 1-3) and run `HOME`.
2. If it stops almost immediately (before reaching the real limit), lower `SGTHRS` further isn't the fix - it likely means the axis hasn't ramped up to a speed where StallGuard's reading is meaningful yet; check `HOME`'s speed argument.
3. If `HOME` fails with "StallGuard never tripped", raise `SGTHRS` until it reliably trips right at the real mechanical limit, not before.

### Physical-unit positioning (LEAD, MOVE)

`Y`/`Z MOVE` takes a distance in millimeters, converted to motor steps via that axis's `LEAD` (millimeters per lead-screw revolution - depends on your actual hardware, so it's configurable, default 4mm) and the firmware's fixed motor/microstep count. `X MOVE` takes an angle in degrees instead, since X turns the turntable directly rather than driving a screw. `A MOVE` also takes degrees, but unlike the open-loop stepper axes, it reads the servo's own absolute position feedback and issues a single absolute goal instead of counting steps.

All four `MOVE` commands are one-shot and relative (signed, from the current position), require the axis not already running/bouncing, and (except X, which has no fixed reference to clamp against) clamp their target to `MIN`/`MAX` so they can't grind past a homed limit.

### Position tracking

X/Y/Z have no position sensor - their `pos` is just an open-loop step count. It's checkpointed to `rig_config.json` periodically while it's changing, and immediately whenever an axis is stopped, so a reboot doesn't lose track of where the mechanism physically is (it isn't saved on every single step, to avoid excessive flash writes). A doesn't need this: the ST3215 servo always reports its own true absolute angle over UART, so `STATUS` just reads it live.

## 3. Component list

| Component | Photo | Description | Docs |
|---|---|---|---|
| **BTT SKR Pico V1.0** | <img src="https://cdn.shopify.com/s/files/1/1619/4791/files/PICO_fa4f69b4-1193-4923-99ba-fb467d87f334.jpg?v=1695350854" width="200"> | RP2040 control board, 2MB flash, 4 onboard TMC2209 drivers (UART, shared bus with MS1/MS2 addressing), USB-C | [GitHub: bigtreetech/SKR-Pico](https://github.com/bigtreetech/SKR-Pico) |
| **ST3215** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/s/t/st3215-servo-1_5.jpg" width="200"> | Serial bus servo (Feetech SMS/STS), 360° magnetic encoder, UART control (single-wire), up to 30 kg·cm torque | [Waveshare Wiki: ST3215 Servo](https://www.waveshare.com/wiki/ST3215_Servo) |
| **NEMA17 34mm** | <img src="https://upload.wikimedia.org/wikipedia/commons/8/83/Nema_17_Stepper_Motor.jpg" width="200"> | Stepper motor, short (34mm) version — lower torque, smaller size/weight, driven by TMC2209 | — |
| **Waveshare Bus Servo Adapter (A)** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/b/u/bus-servo-adapter-a-1_2.jpg" width="200"> | UART (TX/RX) → single-wire half-duplex bus adapter for Feetech/Waveshare servos, powers the servo | [Waveshare Wiki: Bus Servo Adapter (A)](https://www.waveshare.com/wiki/Bus_Servo_Adapter_(A)) |
