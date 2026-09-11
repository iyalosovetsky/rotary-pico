"""Standalone ST3215 move test - moves to a random position and reports
before/after. Run directly on the SKR Pico (Thonny "Run", or
`import move_test` from the REPL).

Status output matches the official Waveshare STServo_Python demos.
"""
import random
import time
from st3215 import ServoBus, ST3215, COMM_SUCCESS, get_result_text, get_error_text

SCS_ID = 1

bus = ServoBus(uart_id=0, tx=0, rx=1, baudrate=1000000)
servo = ST3215(bus, SCS_ID)

model, result, error = servo.ping_verbose()
if result != COMM_SUCCESS:
    print(get_result_text(result))
else:
    print("[ID:%03d] ping Succeeded. SC Servo model number : %d" % (SCS_ID, model))
if error != 0:
    print(get_error_text(error))

if result != COMM_SUCCESS:
    print("aborting - servo not responding")
else:
    servo.torque_enable(True)

    before, result, error = servo.read_position_verbose()
    if result != COMM_SUCCESS:
        print(get_result_text(result))
    else:
        target = random.randint(0, 4095)
        print("[ID:%03d] current position : %d (%.1f deg) -> moving to %d (%.1f deg)" %
              (SCS_ID, before, before * 360 / 4096, target, target * 360 / 4096))

        result, error = servo.set_goal_verbose(target, speed=300)
        if result != COMM_SUCCESS:
            print(get_result_text(result))
        if error != 0:
            print(get_error_text(error))

        time.sleep_ms(100)  # give the servo time to raise its MOVING flag
        while servo.is_moving():
            time.sleep_ms(100)

        after, result, error = servo.read_position_verbose()
        if result != COMM_SUCCESS:
            print(get_result_text(result))
        else:
            print("[ID:%03d] move Succeeded. now at %d (%.1f deg)" %
                  (SCS_ID, after, after * 360 / 4096))
