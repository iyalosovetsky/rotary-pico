#!/usr/bin/env python
"""Minimal ST/SC servo ping test - no interactive keypress prompt, just
open the port, ping the servo, print the result, exit.

Usage: python3 simple_ping.py [device] [id] [baud]
Defaults match the ST3215/SC-series factory settings.
"""
import sys
sys.path.append("..")
from scservo_sdk import PortHandler, sms_sts, COMM_SUCCESS

DEVICENAME = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
SCS_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 1
BAUDRATE = int(sys.argv[3]) if len(sys.argv) > 3 else 1000000

portHandler = PortHandler(DEVICENAME)
packetHandler = sms_sts(portHandler)

if not portHandler.openPort():
    print("Failed to open port", DEVICENAME)
    sys.exit(1)
if not portHandler.setBaudRate(BAUDRATE):
    print("Failed to set baudrate", BAUDRATE)
    sys.exit(1)

model, comm_result, error = packetHandler.ping(SCS_ID)
if comm_result != COMM_SUCCESS:
    print(packetHandler.getTxRxResult(comm_result))
else:
    print("[ID:%03d] ping succeeded, model number: %d" % (SCS_ID, model))
if error != 0:
    print(packetHandler.getRxPacketError(error))

portHandler.closePort()
