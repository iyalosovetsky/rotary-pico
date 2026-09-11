"""Standalone ST3215 move test - moves to a random position and reports
before/after. Run directly on the SKR Pico (Thonny "Run", or
`import move_test` from the REPL).
"""
import random
import time
from st3215 import ServoBus, ST3215

bus = ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)
servo = ST3215(bus, servo_id=1)

if not servo.ping():
    print("ping FAILED - no response, aborting")
else:
    servo.torque_enable(True)
    before = servo.read_position()
    target = random.randint(0, 4095)
    print("current: %d (%.1f deg) -> moving to %d (%.1f deg)" %
          (before, before * 360 / 4096, target, target * 360 / 4096))

    servo.set_goal(target, speed=300)
    while servo.is_moving():
        time.sleep_ms(100)

    after = servo.read_position()
    print("done, now at %d (%.1f deg)" % (after, after * 360 / 4096))
