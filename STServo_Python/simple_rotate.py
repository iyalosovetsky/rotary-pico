#!/usr/bin/env python
"""Minimal ST/SC servo rotation test - reads current position, moves to a
target position, reads position again so you can see it actually moved.

Usage: python3 simple_rotate.py [device] [id] [baud] [target_position] [speed]
Position is a raw register value 0-4095 (0-360 deg). Defaults move to the
middle of the range (2048) at a moderate speed.
"""
import sys
import time
sys.path.append("..")
from scservo_sdk import PortHandler, sms_sts, COMM_SUCCESS

DEVICENAME = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
SCS_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 1
BAUDRATE = int(sys.argv[3]) if len(sys.argv) > 3 else 1000000
TARGET = int(sys.argv[4]) if len(sys.argv) > 4 else 2048
SPEED = int(sys.argv[5]) if len(sys.argv) > 5 else 300
ACC = 50

portHandler = PortHandler(DEVICENAME)
packetHandler = sms_sts(portHandler)

if not portHandler.openPort():
    print("Failed to open port", DEVICENAME)
    sys.exit(1)
if not portHandler.setBaudRate(BAUDRATE):
    print("Failed to set baudrate", BAUDRATE)
    sys.exit(1)

pos, speed, comm_result, error = packetHandler.ReadPosSpeed(SCS_ID)
if comm_result != COMM_SUCCESS:
    print("Read failed:", packetHandler.getTxRxResult(comm_result))
    portHandler.closePort()
    sys.exit(1)
print("current position:", pos)

print("moving to", TARGET, "at speed", SPEED)
packetHandler.WritePosEx(SCS_ID, TARGET, SPEED, ACC)
time.sleep(1.5)

pos2, speed2, comm_result2, error2 = packetHandler.ReadPosSpeed(SCS_ID)
print("new position:", pos2, "speed:", speed2)

portHandler.closePort()
