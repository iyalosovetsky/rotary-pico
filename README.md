*[Українська версія](README.uk.md)*

# rotary-pico

## 1. Description

Control firmware for a DIY turntable rig for a Creality Raptor-style 3D scanner, built on a **BTT SKR Pico** board (RP2040, MicroPython).

- **X axis** — rotates the table (continuous rotation, speed control).
- **Y axis** — moves the scanner carriage over the table (cyclic motion between a lower and upper limit).
- **ST3215 servo** — tilts the scanner head (cyclic motion between a minimum and maximum angle).

All three run concurrently and independently of each other (cooperative multitasking via `uasyncio`), controlled through G-code-like console commands.

The project was inspired by the [Creality Raptor Turntable](https://www.youtube.com/watch?v=kjL7HI78B2U&t=881s) video — `table_models/` contains the turntable models from the same author.

### Project files

| File / folder | Purpose |
|---|---|
| `tmc2209.py` | TMC2209 driver over UART (shared bus, MS1/MS2 addressing) |
| `st3215.py` | ST3215 servo driver (Feetech SMS/STS protocol) |
| `scanner_rig.py` | Orchestrator: async X/Y/servo tasks + console command parser |
| `main.py` | Simple single-motor bench test (bring-up/diagnostics) |
| `freecad/` | Own FreeCAD models (stepper motor, servo mount) |
| `table_models/` | Turntable models (STEP) from the inspiring video's author |

## 2. Command reference

Commands are sent one per line over the console (REPL):

| Command | Description |
|---|---|
| `X SPEED <steps_per_sec>` | Table rotation speed (sign sets direction, 0 = stopped) |
| `X START [CW\|CCW]` | Start table rotation - direction optional, defaults to CW (or last-used) |
| `X STOP` | Stop table rotation |
| `Y MIN <steps>` | Lower limit of carriage travel (microsteps) |
| `Y MAX <steps>` | Upper limit of carriage travel (microsteps) |
| `Y SPEED <steps_per_sec>` | Carriage speed |
| `Y START` | Start cyclic motion between `MIN` and `MAX` |
| `Y STOP` | Stop the carriage |
| `Z MIN <steps>` | Lower limit of Z travel (microsteps) |
| `Z MAX <steps>` | Upper limit of Z travel (microsteps) |
| `Z SPEED <steps_per_sec>` | Z axis speed |
| `Z START` | Start cyclic motion between `MIN` and `MAX` |
| `Z STOP` | Stop the Z axis |
| `A MIN <deg>` | Minimum scanner tilt angle (degrees) |
| `A MAX <deg>` | Maximum scanner tilt angle (degrees) |
| `A SPEED <raw_units>` | Servo speed (raw register units, tune empirically) |
| `A START` | Start cyclic tilt between `MIN` and `MAX` |
| `A STOP` | Stop the servo |
| `STATUS` | Current state of all four axes |
| `HELP` | Command help |

Example session:

```
X SPEED 200
X START
Y MIN 0
Y MAX 3200
Y SPEED 400
Y START
Z MIN 0
Z MAX 3200
Z SPEED 400
Z START
A MIN 30
A MAX 150
A SPEED 300
A START
STATUS
```

## 3. Component list

| Component | Photo | Description | Docs |
|---|---|---|---|
| **BTT SKR Pico V1.0** | <img src="https://cdn.shopify.com/s/files/1/1619/4791/files/PICO_fa4f69b4-1193-4923-99ba-fb467d87f334.jpg?v=1695350854" width="200"> | RP2040 control board, 2MB flash, 4 onboard TMC2209 drivers (UART, shared bus with MS1/MS2 addressing), USB-C | [GitHub: bigtreetech/SKR-Pico](https://github.com/bigtreetech/SKR-Pico) |
| **ST3215** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/s/t/st3215-servo-1_5.jpg" width="200"> | Serial bus servo (Feetech SMS/STS), 360° magnetic encoder, UART control (single-wire), up to 30 kg·cm torque | [Waveshare Wiki: ST3215 Servo](https://www.waveshare.com/wiki/ST3215_Servo) |
| **NEMA17 34mm** | <img src="https://upload.wikimedia.org/wikipedia/commons/8/83/Nema_17_Stepper_Motor.jpg" width="200"> | Stepper motor, short (34mm) version — lower torque, smaller size/weight, driven by TMC2209 | — |
| **Waveshare Bus Servo Adapter (A)** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/b/u/bus-servo-adapter-a-1_2.jpg" width="200"> | UART (TX/RX) → single-wire half-duplex bus adapter for Feetech/Waveshare servos, powers the servo | [Waveshare Wiki: Bus Servo Adapter (A)](https://www.waveshare.com/wiki/Bus_Servo_Adapter_(A)) |
