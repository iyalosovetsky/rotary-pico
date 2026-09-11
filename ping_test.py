"""Standalone ST3215 ping test - run directly on the SKR Pico
(Thonny "Run", or `import ping_test` from the REPL).
"""
from st3215 import ServoBus, ST3215

bus = ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)
servo = ST3215(bus, servo_id=1)

if servo.ping():
    print("ping OK")
    pos = servo.read_position()
    print("position: %d (%.1f deg)" % (pos, pos * 360 / 4096))
else:
    print("ping FAILED - no response (check wiring/jumper/power)")
