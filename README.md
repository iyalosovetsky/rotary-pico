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

Commands are sent one per line over the console (REPL). `MIN`/`MAX`/`SPEED`/`SGTHRS`/`LEAD`/`MICROSTEPS`/`CURRENT` with no value (e.g. `Y MIN`, not `Y MIN 0`) print that field's current value instead of setting it.

| Command | Description |
|---|---|
| `START [minutes]` | Start every axis at once (using whatever they're each already configured with), auto-stop after `minutes` (default 5) |
| `STOP` | Stop every axis immediately |
| `SLEEP` | Stop everything, disable the X/Y/Z drivers, release servo torque (see below) |
| `WAKE` | Undo `SLEEP` by hand (see below) |
| `X SPEED <steps_per_sec>` | Table rotation speed (sign sets direction, 0 = stopped) |
| `X START [CW\|CCW]` | Start table rotation - direction optional, defaults to CW (or last-used) |
| `X STOP` | Stop table rotation |
| `X MIN <deg>` | Default 0 - only used by `MOVE MIN`/`MID` (see below), not a limit on plain numeric `MOVE` |
| `X MAX <deg>` | Default 180 - only used by `MOVE MAX`/`MID` (see below), not a limit on plain numeric `MOVE` |
| `X MOVE <deg\|MIN\|MAX\|MID>` | A number is an unclamped signed relative rotation (multi-revolution moves like `720` are fine) - axis must be stopped first. `MIN`/`MAX`/`MID` go straight to that angle instead (see below) |
| `X ZERO` | Make the current position 0 (see below) |
| `X MICROSTEPS <n>` | Driver microstep resolution: one of 256/128/64/32/16/8/4/2/1 (see below) |
| `X CURRENT <mA>` | Run current for this axis's driver (hold current is auto-derived as half) |
| `X TMC` | TMC2209 driver health: faults, live current, microsteps, mode (see below) |
| `Y MIN <mm>` | Lower limit of carriage travel, in millimeters (via `LEAD`) - default 0 |
| `Y MAX <mm>` | Upper limit of carriage travel, in millimeters (via `LEAD`) - default 4 |
| `Y SPEED <steps_per_sec>` | Carriage speed |
| `Y SGTHRS <0-255>` | StallGuard sensorless-homing threshold (see below) - higher trips more easily |
| `Y HOME [DEC\|INC] [speed]` | One-shot calibration: home toward a StallGuard stall (see below) |
| `Y LEAD <mm>` | Lead screw pitch (mm per screw revolution) - used to convert `MOVE`'s millimeters to steps |
| `Y MOVE <mm\|MIN\|MAX\|MID>` | One-shot move: a signed relative distance in mm (clamped to `MIN`/`MAX`), or straight to `MIN`/`MAX`/the midpoint - axis must be stopped first |
| `Y ZERO` | Make the current position 0 (see below) |
| `Y MICROSTEPS <n>` | Driver microstep resolution: one of 256/128/64/32/16/8/4/2/1 (see below) |
| `Y CURRENT <mA>` | Run current for this axis's driver (hold current is auto-derived as half) |
| `Y TMC` | TMC2209 driver health: faults, live current, microsteps, mode (see below) |
| `Y START` | Start cyclic motion between `MIN` and `MAX` |
| `Y STOP` | Stop the carriage |
| `Z MIN <mm>` | Lower limit of Z travel, in millimeters (via `LEAD`) - default 0 |
| `Z MAX <mm>` | Upper limit of Z travel, in millimeters (via `LEAD`) - default 4 |
| `Z SPEED <steps_per_sec>` | Z axis speed |
| `Z SGTHRS <0-255>` | StallGuard sensorless-homing threshold (see below) - higher trips more easily |
| `Z HOME [DEC\|INC] [speed]` | One-shot calibration: home toward a StallGuard stall (see below) |
| `Z LEAD <mm>` | Lead screw pitch (mm per screw revolution) - used to convert `MOVE`'s millimeters to steps |
| `Z MOVE <mm\|MIN\|MAX\|MID>` | One-shot move: a signed relative distance in mm (clamped to `MIN`/`MAX`), or straight to `MIN`/`MAX`/the midpoint - axis must be stopped first |
| `Z ZERO` | Make the current position 0 (see below) |
| `Z MICROSTEPS <n>` | Driver microstep resolution: one of 256/128/64/32/16/8/4/2/1 (see below) |
| `Z CURRENT <mA>` | Run current for this axis's driver (hold current is auto-derived as half) |
| `Z TMC` | TMC2209 driver health: faults, live current, microsteps, mode (see below) |
| `Z START` | Start cyclic motion between `MIN` and `MAX` |
| `Z STOP` | Stop the Z axis |
| `A MIN <deg>` | Minimum scanner tilt angle (degrees) |
| `A MAX <deg>` | Maximum scanner tilt angle (degrees) |
| `A SPEED <raw_units>` | Servo speed (raw register units, tune empirically) |
| `A MOVE <deg\|MIN\|MAX\|MID>` | One-shot move: a signed relative angle in degrees (clamped to `MIN`/`MAX`), or straight to `MIN`/`MAX`/the midpoint - axis must be stopped first |
| `A TMC` | Servo health: voltage, temperature, load, current, error flags (see below) |
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

Or straight to a limit instead of a relative distance:

```
Y MOVE MIN
Y MOVE MAX
Y MOVE MID
A MOVE MID
```

### Y/Z sensorless homing (StallGuard)

Y and Z have no physical endstop switches. Instead, `HOME` deliberately drives the axis toward one end (`DEC` = decreasing position, `INC` = increasing; Y defaults to `DEC`, Z to `INC`) while polling the TMC2209's StallGuard result (`SG_RESULT`) over UART - it drops as motor load rises, so driving into a real mechanical stop reads as a stall. Once that happens, `MIN` (for a `DEC` stall) or `MAX` (for an `INC` stall) is set to the position it stalled at.

This is a one-shot calibration - run `HOME` once before the first `START`, the way Klipper/Voron-style sensorless homing works. Ordinary bouncing afterward does **not** re-check StallGuard on every move: it runs the quieter stealthChop mode at full current, under which the StallGuard signal isn't reliable enough to act on. `HOME` switches to spreadCycle and a reduced current just for the homing move, then restores normal settings afterward.

`SGTHRS` has no universal default - it's specific to your motor, current, speed and mechanics, and must be tuned by hand:

1. Set a low `SGTHRS` (e.g. 1-3) and run `HOME`.
2. If it stops almost immediately (before reaching the real limit), lower `SGTHRS` further isn't the fix - it likely means the axis hasn't ramped up to a speed where StallGuard's reading is meaningful yet; check `HOME`'s speed argument.
3. If `HOME` fails with "StallGuard never tripped", raise `SGTHRS` until it reliably trips right at the real mechanical limit, not before.

### Zeroing the origin (ZERO)

`X`/`Y`/`Z ZERO` does the same zeroing `HOME` does (current position becomes 0, `MIN`/`MAX` shift by the same offset so they keep meaning the same real distance from the new origin) but instantly, wherever the axis currently is - no motion, no StallGuard involved. Use it to redefine the origin by hand instead of (or in addition to) a StallGuard-based `HOME`. X has no `HOME` at all (continuous rotation, nothing to stall against), so `ZERO` is its only way to get a zero reference.

### Physical-unit positioning (LEAD, MOVE)

`Y`/`Z MOVE` takes a distance in millimeters, converted to motor steps via that axis's `LEAD` (millimeters per lead-screw revolution - depends on your actual hardware, so it's configurable, default 4mm) and that axis's own `MICROSTEPS` setting (see below). `X MOVE` takes an angle in degrees instead, since X turns the turntable directly rather than driving a screw. `A MOVE` also takes degrees, but unlike the open-loop stepper axes, it reads the servo's own absolute position feedback and issues a single absolute goal instead of counting steps.

All four `MOVE` commands are one-shot and require the axis not already running/bouncing. Given a number, `MOVE` is a signed relative move from the current position - clamped to `MIN`/`MAX` for Y/Z/A (`MIN`/`MAX` are millimeters for Y/Z, same as `MOVE`, and degrees for A), but **not** for X: X is continuous rotation, so a plain numeric `X MOVE` is deliberately unbounded, letting multi-revolution moves like `X MOVE 720` (two full turns) through untouched. Given `MIN`, `MAX`, or `MID` instead of a number, all four axes go straight to that limit (or the midpoint between them) from wherever they currently are - an absolute move, not a relative one; this is the only thing X's own `MIN`/`MAX` (in degrees, default 0/180 so `MID` = 90) are used for.

### Microstepping and current (MICROSTEPS, CURRENT)

Each of X/Y/Z has its own configurable `MICROSTEPS` (one of 256/128/64/32/16/8/4/2/1, default 16) and `CURRENT` (run current in mA - hold current is always auto-derived as half of it), persisted independently per axis. Changing `MICROSTEPS` rescales `pos`/`MIN`/`MAX` by the resolution ratio (e.g. 16→32 doubles them): a single step means a different real distance at a different resolution, so without rescaling, an existing `HOME` calibration would silently stop matching reality instead of just needing conversion. `CURRENT` is independent of `HOME_CURRENT_MA` in `scanner_rig.py`, which only applies transiently during the `HOME` move itself and is restored to this per-axis `CURRENT` afterward.

### Driver/servo health (TMC)

`X`/`Y`/`Z TMC` decodes that TMC2209's GSTAT/DRV_STATUS registers into a one-line health summary: `OK`, or `ERROR(...)` listing any of `RESET`/`DRV_ERR`/`UV_CP` (GSTAT) or `OTPW`/`OT`/`S2GA`/`S2GB`/`S2VSA`/`S2VSB`/`OLA`/`OLB` (DRV_STATUS) that are set, plus the driver's live actual current in mA, its microsteps (read back from the chip, not assumed), mode (stealthChop/spreadCycle), standstill, and - for Y/Z - `sgthrs=N(cfg)` (SGTHRS can't be read back from this chip, so this echoes the last value configured in software, not a hardware readback). `RESET` is expected once right after power-up; GSTAT is cleared on each read so it doesn't keep reporting an old event. See [TMC2209_REGISTERS.md](TMC2209_REGISTERS.md) for the full register/bit reference.

`A TMC` reads the ST3215's own feedback registers (voltage, temperature, load, current) plus the status/error byte every reply carries, decoded the same way: `OK`, or `ERROR(...)` listing any of `VOLTAGE`/`ANGLE`/`OVERHEAT`/`OVERELE`/`OVERLOAD`. `load` is a raw signed magnitude, not a calibrated percentage - see [ST3215_REGISTERS.md](ST3215_REGISTERS.md).

Both are useful for catching a motor/servo that's silently drawing less current or running hotter than expected, without pulling a multimeter.

### Position tracking

X/Y/Z have no position sensor - their `pos` is just an open-loop step count. It's checkpointed to `rig_config.json` every 10 minutes while it's changing, and immediately whenever an axis is stopped or the rig goes to `SLEEP`, so a reboot doesn't lose track of where the mechanism physically is. That interval is long on purpose: writing to flash blocks the whole program for 50-100+ms (measured on real hardware) - MicroPython's flash writes are synchronous, so nothing else (including the step timing of whatever's moving) can run until it returns. At a much shorter interval this was a felt stutter during continuous motion; `STOP`/`SLEEP` cover the common "about to sit idle" case immediately instead of waiting on the timer. A doesn't need any of this: the ST3215 servo always reports its own true absolute angle over UART, so `STATUS` just reads it live.

### Idle power-down (SLEEP, WAKE)

`SLEEP` stops every axis, then disables the X/Y/Z TMC2209 drivers outright (their `EN` pin - no holding current at all, quieter and cooler than just standing still with the normal hold current) and releases the ST3215's torque. It happens either by typing `SLEEP` yourself, or automatically after 20 minutes with no console input at all and nothing running (checked periodically - it never fires while any axis is actually moving, no matter how stale the last-input time is).

Any `START`, `MOVE`, or `HOME` command, for any axis, wakes everything back up first, the same as typing `WAKE` directly. Commands that don't cause movement (`SPEED`, `MIN`/`MAX`, `TMC`, `STATUS`, etc.) leave it asleep and still work fine - UART communication with the TMC2209s doesn't depend on the `EN` pin.

Because a torque-less servo can sag under the weight of whatever it's holding, `WAKE` compares the servo's angle against what it was right before `SLEEP` and, if it moved by more than a degree, commands it back to where it was. X/Y/Z don't get this treatment: nothing in this rig loads them with enough gravity to drift while unpowered, and even if it did, there's no sensor on those axes to detect it - that's the whole reason `SLEEP` disables them rather than tracking drift the way it does for the servo.

## 3. Component list

| Component | Photo | Description | Docs |
|---|---|---|---|
| **BTT SKR Pico V1.0** | <img src="https://cdn.shopify.com/s/files/1/1619/4791/files/PICO_fa4f69b4-1193-4923-99ba-fb467d87f334.jpg?v=1695350854" width="200"> | RP2040 control board, 2MB flash, 4 onboard TMC2209 drivers (UART, shared bus with MS1/MS2 addressing), USB-C | [GitHub: bigtreetech/SKR-Pico](https://github.com/bigtreetech/SKR-Pico) |
| **ST3215** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/s/t/st3215-servo-1_5.jpg" width="200"> | Serial bus servo (Feetech SMS/STS), 360° magnetic encoder, UART control (single-wire), up to 30 kg·cm torque | [Waveshare Wiki: ST3215 Servo](https://www.waveshare.com/wiki/ST3215_Servo) |
| **NEMA17 34mm** | <img src="https://upload.wikimedia.org/wikipedia/commons/8/83/Nema_17_Stepper_Motor.jpg" width="200"> | Stepper motor, short (34mm) version — lower torque, smaller size/weight, driven by TMC2209 | — |
| **Waveshare Bus Servo Adapter (A)** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/b/u/bus-servo-adapter-a-1_2.jpg" width="200"> | UART (TX/RX) → single-wire half-duplex bus adapter for Feetech/Waveshare servos, powers the servo | [Waveshare Wiki: Bus Servo Adapter (A)](https://www.waveshare.com/wiki/Bus_Servo_Adapter_(A)) |
