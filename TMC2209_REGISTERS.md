*[Українська версія](TMC2209_REGISTERS.uk.md)*

# TMC2209 register reference

Every register `tmc2209.py` actually reads or writes, why, and what the relevant bits mean. This is not a full transcription of the datasheet - only what this codebase touches. For anything not covered here, see the official datasheet:

**[TMC2209 Datasheet, Rev. 1.09](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2209_datasheet_rev1.09.pdf)** (Analog Devices / Trinamic Motion Control). Section numbers below (e.g. "5.5.3") refer to this document.

## Datagram protocol (how `tmc2209.py` talks to the chip)

All 4 on-board drivers share one UART bus, distinguished by a node address (0-3) set via each chip's MS1/MS2 strapping. Datasheet section 5, "UART Single Wire Interface":

- **Write** (8 bytes): `sync(0x05) | addr | reg|0x80 | data[3] | data[2] | data[1] | data[0] | CRC8`
- **Read request** (4 bytes): `sync(0x05) | addr | reg&0x7F | CRC8`, chip replies with an 8-byte datagram: `sync(0x05) | 0xFF(master addr) | reg | data[3..0] | CRC8`
- CRC8 uses the polynomial 0x07 (bit-reversed), implemented in `_crc8()`.
- TX is wired into RX through a resistor on this board (BTT SKR Pico), so **every transmitted byte echoes back** and must be drained before reading a real reply - see `TMC2209Bus._flush_rx()`/`_read_exact()`.

## Register table

| Addr | Register | Access | Used for |
|---|---|---|---|
| 0x00 | GCONF | R+W | UART mode setup (`pdn_disable`, `mstep_reg_select`), stealthChop/spreadCycle select |
| 0x01 | GSTAT | R+WC | Driver health: reset/overtemp-or-short/undervoltage flags - `diag_summary()` |
| 0x06 | IOIN | R | Chip version check (`check_connection()`) |
| 0x10 | IHOLD_IRUN | **W (write-only)** | Run/hold current (`set_current()`) |
| 0x13 | TPWMTHRS | W | Declared, not currently used by this codebase |
| 0x14 | TCOOLTHRS | **W (write-only)** | StallGuard/CoolStep minimum-speed threshold (`enable_stallguard()`) |
| 0x40 | SGTHRS | **W (write-only)** | StallGuard stall threshold (`enable_stallguard()`) |
| 0x41 | SG_RESULT | R | Live StallGuard load reading, polled during `HOME` (`read_stallguard_result()`) |
| 0x6C | CHOPCONF | R+W | Microstep resolution / MRES field (`set_microsteps()`, `read_microsteps()`) |
| 0x6F | DRV_STATUS | R | Fault flags, live current scale, mode, standstill - `diag_summary()` |
| 0x70 | PWMCONF | R+W | stealthChop `pwm_autoscale`/`pwm_autograd` bits (`enable_uart_mode()`) |

**R+WC** = read, write-clear: writing `1` to a bit clears it (used for GSTAT - see `clear_gstat()`).

### Write-only registers: don't try to verify them by reading back

IHOLD_IRUN, TCOOLTHRS, and SGTHRS are marked **W** in the datasheet's register access table - the chip does not return their contents on a read, regardless of whether the write succeeded. Reading any of them back always returns `0x00000000`. This tripped up an earlier debugging session in this project (documented in [TROUBLESHOOTING.md](TROUBLESHOOTING.md)): a `0x00000000` readback on these three was mistaken for a failed write, when the writes had actually succeeded all along. Only GCONF/CHOPCONF/PWMCONF (all R+W) are meaningful to read back for verification.

This is also why `X/Y/Z TMC`'s `sgthrs=N(cfg)` in `scanner_rig.py` is labeled `(cfg)`: it's the value the software last configured the register to, not something read from the chip.

## GCONF (0x00) bits used here

| Bit | Name (as used in this code) | Meaning |
|---|---|---|
| 2 | `en_spreadcycle` (`spreadcycle` param to `enable_uart_mode()`) | 0 = stealthChop (quiet, used for normal bouncing), 1 = spreadCycle (used only during `HOME`, where StallGuard needs a clean signal) |
| 6 | `pdn_disable` | Must be set for UART operation (frees the PDN_UART pin from its pin-down/analog-select role) |
| 7 | `mstep_reg_select` | Must be set so microstep resolution comes from CHOPCONF's MRES field (register control) instead of the MS1/MS2 pins |

## GSTAT (0x01) bits - datasheet "general configuration registers" table

| Bit | Name | Meaning |
|---|---|---|
| 0 | `reset` | IC has been reset since the last GSTAT read - expected once right after power-up |
| 1 | `drv_err` | Driver shut down due to overtemperature or short-circuit (see DRV_STATUS for which) |
| 2 | `uv_cp` | Undervoltage on the charge pump - driver disabled while this is set |

## DRV_STATUS (0x6F) bits - datasheet section 5.5.3

| Bit | Name | Meaning |
|---|---|---|
| 0 | `otpw` | Overtemperature pre-warning |
| 1 | `ot` | Overtemperature shutdown |
| 2 | `s2ga` | Short to ground, phase A |
| 3 | `s2gb` | Short to ground, phase B |
| 4 | `s2vsa` | Low-side short, phase A |
| 5 | `s2vsb` | Low-side short, phase B |
| 6 | `ola` | Open load, phase A (informative only - the datasheet notes false positives during fast motion/standstill; check during slow motion) |
| 7 | `olb` | Open load, phase B (same caveat) |
| 8-11 | `t120`/`t143`/`t150`/`t157` | Temperature threshold comparators - not decoded by `diag_summary()` (otpw/ot cover the practically useful cases) |
| 16-20 | `cs_actual` | Live current-scale (0-31) actually applied - converted to mA by `cs_to_ma()`, the inverse of `set_current()`'s formula. This is `IHOLD`'s scale while `standstill=1`, `IRUN`'s while moving - not simply "whatever `set_current()` was last called with" |
| 30 | `stealth` | 1 = stealthChop active, 0 = spreadCycle |
| 31 | `stst` | Standstill: motor has been stopped for 2^20 clocks |

## IHOLD_IRUN (0x10) layout

| Bits | Field | Notes |
|---|---|---|
| 4:0 | `IHOLD` | Hold current scale (0-31), applied at standstill |
| 12:8 | `IRUN` | Run current scale (0-31), applied while moving |
| 19:16 | `IHOLDDELAY` | Delay (in units of ~2^18 clocks) before ramping down from IRUN to IHOLD after motion stops |

Current-scale (CS) formula used by `set_current()`/`cs_to_ma()` (`_ma_to_cs`/`cs_to_ma` in `tmc2209.py`), the standard Trinamic formula:

```
CS = round(32 * sqrt(2) * I_rms_amps * (Rsense + 0.02) / Vfs - 1)   # clamped to 0-31
Vfs = 0.180 if vsense else 0.325
```

`Rsense`/`vsense` are constructor args on `TMC2209` (default `rsense=0.11, vsense=False`, matching the BTT SKR Pico's onboard drivers) - not hardcoded into the formula, in case a different board/driver current-sense config is ever used.

## CHOPCONF (0x6C): MRES field (bits 27:24)

`set_microsteps()`/`read_microsteps()` only touch this field, preserving every other CHOPCONF bit (read-modify-write):

| MRES | Microsteps |
|---|---|
| 0 | 256 |
| 1 | 128 |
| 2 | 64 |
| 3 | 32 |
| 4 | 16 (this rig's default - see `MICROSTEPS` in `scanner_rig.py`) |
| 5 | 8 |
| 6 | 4 |
| 7 | 2 |
| 8 | 1 (full step) |

## PWMCONF (0x70) bits used here

| Bit | Name | Meaning |
|---|---|---|
| 18 | `pwm_autoscale` | stealthChop's current-regulation loop adapts PWM amplitude to the actual motor/load, instead of running open-loop off reset defaults |
| 19 | `pwm_autograd` | Automatic tuning of the PWM gradient, used together with `pwm_autoscale` |

Both are set by `enable_uart_mode()` via read-modify-write, leaving the factory `pwm_freq`/`pwm_grad`/`pwm_ofs` defaults untouched.
