"""Standalone ST3215 ping test - run directly on the SKR Pico
(Thonny "Run", or `import ping_test` from the REPL).

Status output matches the official Waveshare STServo_Python/ping.py demo.
"""
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
