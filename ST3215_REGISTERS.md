*[Українська версія](ST3215_REGISTERS.uk.md)*

# ST3215 register reference

Every register `st3215.py` actually reads or writes, why, and what units/scaling apply. This is not a full transcription of the datasheet - only what this codebase touches. Addresses were verified against the official Feetech/Waveshare SDK vendored in this repo (`scservo_sdk/sms_sts.py`, from [ftservo/FTServo_Python](https://github.com/ftservo/FTServo_Python)) and the [`parallax/scservo`](https://github.com/parallaxinc/scservo) reference. For anything not covered here:

- **[Feetech STS3215 official product specification (PDF)](https://www.feetechrc.com/Data/feetechrc/upload/file/20200611/6372749961523760249976542.pdf)** (mirror: [seeedstudio.com](https://files.seeedstudio.com/products/Feetech/108090023_STS3215-C001_Datasheet.pdf))
- **[Waveshare Wiki: ST3215 Servo](https://www.waveshare.com/wiki/ST3215_Servo)**

## Packet protocol (how `st3215.py` talks to the servo)

Feetech SMS/STS protocol, packet-based, checksum instead of CRC:

- Packet: `0xFF 0xFF | id | length | instruction | params... | checksum`
- `checksum = (~(id + length + instruction + sum(params))) & 0xFF`
- Instructions used here: `PING (1)`, `READ (2)`, `WRITE (3)`
- Unlike the TMC2209 bus (a bare resistor tying TX into RX, so every byte echoes and must be drained), the Waveshare Bus Servo Adapter (A) is a real transceiver - TX/RX stay electrically separate, so there is **no self-echo** to drain on this bus. See `st3215.py`'s module docstring and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the bug this distinction caused when the TMC2209 bus's echo-drain pattern was copied here by mistake.
- Every reply carries a status/error byte (`reply[4]`), decoded by `get_error_text()` into the `ERRBIT_*` flags below - this is what `diag_summary()`'s `ERROR(...)` list comes from.

## Register table

| Addr | Register | Bytes | Access | Used for |
|---|---|---|---|---|
| 3 | MODEL_L (+4: MODEL_H) | 2 | R | Model number (`ping_verbose()`) |
| 9 | MIN_ANGLE_LIMIT_L (+10: _H) | 2 | R/W (EPROM) | Declared, not currently used by this codebase |
| 11 | MAX_ANGLE_LIMIT_L (+12: _H) | 2 | R/W (EPROM) | Declared, not currently used by this codebase |
| 33 | MODE | 1 | R/W (EPROM) | Declared, not currently used by this codebase |
| 40 | TORQUE_ENABLE | 1 | R/W | Enable/disable torque (`torque_enable()`) |
| 41 | ACC | 1 | R/W | Acceleration, raw units 0-254 (`set_acceleration()`) - exact accel-per-unit isn't documented consistently, calibrate by eye |
| 42 | GOAL_POSITION_L (+43: _H) | 2 | R/W | Target position (`set_goal()`/`set_goal_deg()`) |
| 44 | GOAL_TIME_L (+45: _H) | 2 | R/W | Move duration; left at 0 by this driver so the servo uses GOAL_SPEED instead of a fixed time |
| 46 | GOAL_SPEED_L (+47: _H) | 2 | R/W | Move speed, raw servo-internal units (~0-3400 typical) |
| 56 | PRESENT_POSITION_L (+57: _H) | 2 | R | Live absolute position (`read_position()`/`read_position_deg()`) |
| 60 | PRESENT_LOAD_L (+61: _H) | 2 | R | Live load: bits 0-9 magnitude, bit 10 direction (`read_load()`) - see note below |
| 62 | PRESENT_VOLTAGE | 1 | R | Live supply voltage, raw × 0.1 = volts (`read_voltage()`) |
| 63 | PRESENT_TEMPERATURE | 1 | R | Live temperature, raw value is already °C (`read_temperature()`) |
| 66 | MOVING | 1 | R | Whether the servo is currently moving (`is_moving()`) |
| 69 | PRESENT_CURRENT_L (+70: _H) | 2 | R | Live current draw, raw × 6.5 = mA (`read_current_ma()`) |

**EPROM** registers persist across power cycles but require the EPROM to be unlocked (`LockEprom`/`unLockEprom` in the official SDK - not implemented in `st3215.py`, since this driver never writes them).

### PRESENT_LOAD: magnitude is not independently confirmed as a percentage

Some community register references describe PRESENT_LOAD as 0-1000 representing 0-100.0% of maximum torque, but this wasn't found stated plainly enough in the official spec to rely on. `read_load()` therefore returns the raw signed magnitude (0-1023, negative when the direction bit is set) rather than asserting a percentage scale it can't back up.

## Status/error byte (`ERRBIT_*` in `st3215.py`)

Returned as byte index 4 of every reply packet - not a separately-addressed register, but the closest equivalent to the TMC2209's GSTAT/DRV_STATUS fault flags, and what `diag_summary()`'s `ERROR(...)` list is built from:

| Bit | Constant | Meaning |
|---|---|---|
| 0 | `ERRBIT_VOLTAGE` | Input voltage error |
| 1 | `ERRBIT_ANGLE` | Angle sensor error |
| 2 | `ERRBIT_OVERHEAT` | Overheat error |
| 3 | `ERRBIT_OVERELE` | Over-electrical-current (OverEle) error |
| 5 | `ERRBIT_OVERLOAD` | Overload error |

These match the official Waveshare/Feetech `scservo_sdk` (`protocol_packet_handler.py`)'s error-bit constants, which is why `get_result_text()`/`get_error_text()` read the same as the vendored `STServo_Python` demo scripts' own output.

## Position/angle conversion

`UNITS_PER_REV = 4096` (12-bit position sensor, magnetic encoder, one full 360° turn):

```
deg_to_units(deg) = round(deg / 360 * 4096), clamped to 0..4095
units_to_deg(units) = units * 360 / 4096
```
