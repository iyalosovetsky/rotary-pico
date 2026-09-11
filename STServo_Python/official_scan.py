import sys
sys.path.append("..")
from scservo_sdk import *

DEVICENAME = "/dev/ttyACM0"

for baud in [1000000, 115200, 500000, 250000, 57600, 38400, 19200, 9600]:
    portHandler = PortHandler(DEVICENAME)
    packetHandler = sms_sts(portHandler)
    if not portHandler.openPort():
        print("baud=%d: failed to open port" % baud)
        continue
    if not portHandler.setBaudRate(baud):
        print("baud=%d: failed to set baud" % baud)
        portHandler.closePort()
        continue
    found = False
    for sid in range(10):
                    
        #print('try',baud, sid)
        model, res, err = packetHandler.ping(sid)
        if res == COMM_SUCCESS:
            print("baud=%d: FOUND id=%d model=%d" % (baud, sid, model))
            found = True
    if not found:
        print("baud=%d: nothing" % baud)
    portHandler.closePort()
print("done")
