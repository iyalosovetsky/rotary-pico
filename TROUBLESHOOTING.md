*[Українська версія](TROUBLESHOOTING.uk.md)*

# Troubleshooting log

## ST3215 servo: no response on the bus (unresolved — hardware fault)

**Symptom:** after wiring the ST3215 servo through a Waveshare Bus Servo Adapter (A) into the SKR Pico's `Laser` connector (IO0/IO1, see `PINOUT.md`), `scanner_rig.py`/`st3215.py` got `OSError: no reply` on every call — `ping()`, `read_position()`, `set_goal_deg()`.

**Diagnostic steps, in order, each ruling something out:**

1. **Adapter jumper position** — confirmed set to `A` (required for external-MCU UART mode, as opposed to `B` which routes the adapter's own USB port instead). Correct.
2. **Adapter power** — power LED on the adapter lit. Confirmed powered.
3. **TX/RX crossing** — confirmed SKR Pico TX (IO0) → adapter RX, SKR Pico RX (IO1) → adapter TX (not straight-through). Correct.
4. **MCU-side loopback test** — shorted IO0 and IO1 together directly at the SKR Pico connector (adapter disconnected) and sent raw bytes over `UART(0, tx=Pin(0), rx=Pin(1))`. Bytes echoed back correctly → **RP2040 pins/UART0 hardware confirmed fully healthy**, ruling out the MCU entirely.
5. **Baud rate sweep** — tried all 9 standard SC/STS baud rates (1000000, 500000, 250000, 115200, 76800, 57600, 38400, 19200, 9600) with broadcast + narrow ID scan. No response at any rate.
6. **Servo power** — an LED lit inside the servo itself, confirming VCC/GND reach the servo's control board.
7. **Cable swap** — replaced the servo bus cable. No change.
8. **Full servo ID sweep** — scanned all 254 possible IDs (0-253) at the two most likely baud rates (1000000, 115200) using `st3215.py`. Nothing responded.
9. **Independent verification with the official Waveshare SDK** — disconnected the SKR Pico entirely, plugged the adapter directly into a PC via USB (it exposes its own USB-serial chip), fetched the official `scservo_sdk` (from [ftservo/FTServo_Python](https://github.com/ftservo/FTServo_Python), now vendored in `scservo_sdk/`) and ran the stock `STServo_Python/ping.py` example against it. Result: **`[TxRxResult] There is no status packet!`** — identical failure, from Waveshare's own code, completely independent of the SKR Pico, MicroPython, or this repo's `st3215.py`.

**Conclusion:** the custom `st3215.py` driver is confirmed correct (the official SDK fails identically). The SKR Pico, its GPIO pins, and the wiring/crossing/jumper are all confirmed healthy. The fault is physically located somewhere in **adapter ↔ cable ↔ servo** — most likely the adapter's signal-line circuitry or the servo's own UART transceiver, since the power/VCC path is confirmed working on both ends (LEDs lit) while the signal path carries nothing at all, even after a cable swap.

**Not yet tried (next steps if this comes up again):**
- Continuity-check the Signal line specifically with a multimeter, adapter port to servo connector.
- Swap in a different servo or a different adapter board, if available, to isolate which specific unit is at fault.
- Try the adapter's other servo port, if it has more than one.

## Setup notes for the official Waveshare SDK (`STServo_Python/`)

The demo scripts in `STServo_Python/` came from Waveshare without their `scservo_sdk` dependency — it's vendored separately in `scservo_sdk/` (fetched from the official `ftservo/FTServo_Python` repo) so `sys.path.append("..")` + `from scservo_sdk import *` resolves.

Each script hardcodes `DEVICENAME` (Windows `COM*` by default) — set it to the actual device, e.g. `/dev/ttyACM0` on Linux.

`ping.py` (and others) use `termios` at import time to support a "press any key" prompt, which throws `termios.error: (25, 'Inappropriate ioctl for device')` if stdin isn't a real TTY (e.g. run from a non-interactive script/CI). Run interactively, or wrap with `script -qec "python3 ping.py" /dev/null` to allocate a pseudo-terminal.
