*[Українська версія](PINOUT.uk.md)*

# BTT SKR Pico V1.0 — Pinout

GPIO numbering and connector assignments cross-checked against the official [bigtreetech/SKR-Pico](https://github.com/bigtreetech/SKR-Pico) diagram (`Klipper/Images/pinout.png`). The "In this project" column shows how each pin is actually used here (`tmc2209.py`, `st3215.py`, `scanner_rig.py`).

## Stepper motors

| Axis | EN | STEP | DIR | UART address | In this project |
|---|---|---|---|---|---|
| X | IO12 | IO11 | IO10 | 0 | Table — continuous rotation |
| Y | IO7 | IO6 | IO5 | 2 | Scanner carriage — bounces between MIN/MAX |
| Z | IO2 | IO19 | IO28 | 1 | unused |
| E0 | IO15 | IO14 | IO13 | 3 | unused |

**Motor UART (shared bus, all 4 drivers):** TX = IO8, RX = IO9

## Endstops

| Connector | Signal | In this project |
|---|---|---|
| X-STOP | IO4 | free (open-loop motion, no homing) |
| Y-STOP | IO3 | free |
| Z-STOP | IO25 | free |
| E0-STOP | IO16 | free |

## Thermistors / heaters

| Connector | Signal | In this project |
|---|---|---|
| TH0 | IO27 | unused |
| THB | IO26 | unused |
| HE (hotend heater) | IO23 | unused |
| HB (bed heater) | IO21 | unused |

## Fans

| Connector | Signal | In this project |
|---|---|---|
| FAN1 | IO17 | free |
| FAN2 | IO18 | free |
| FAN3 | IO20 | free |

## Other

| Connector | Signal(s) | In this project |
|---|---|---|
| RGB (Neopixel) | IO24 | unused |
| PROBE | IO22 | free (BLTouch-style signal) |
| SERVOS | IO29 | free (1 PWM pin — **not suitable** for ST3215 UART, which needs 2 lines) |
| **Laser** | **IO0 (TX), IO1 (RX)**, GND, 5V | **ST3215 servo bus** via the Waveshare Bus Servo Adapter (A) — these are the exact pins used in `scanner_rig.py` (`ServoBus(uart_id=0, tx=0, rx=1)`). ⚠️ The TX/RX silkscreen labels on this particular adapter board are swapped (mislabeled) — go by what actually works, not the printed labels. |
| Power | GND, 12/24V | board/driver power input |
| USB | USB_DP (D+), USB_DM (D-), Type-C | console/REPL, logic power |

## Free pins for expansion

Z (`step=IO19 dir=IO28 en=IO2`, addr=1) and E0 (`step=IO14 dir=IO13 en=IO15`, addr=3) are fully free motor channels on the same TMC2209 UART bus, in case another axis is needed (e.g. a separate focus mechanism). Endstops, thermistors, heaters, FAN1-3, RGB, and PROBE are also free.
