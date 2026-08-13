"""Keeps this Windows machine from sleeping while plugged into AC power.

Runs forever (meant to be started at logon by a Scheduled Task). Does NOT
affect the screen lock/screensaver timeout -- only prevents the deeper
system sleep state, which is what breaks the ColosseumTicketMonitor task on
a laptop that hibernates behind a BitLocker pre-boot PIN. On battery power
it releases the request and lets the machine sleep normally.
"""

import ctypes
import time

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

CHECK_INTERVAL_SECONDS = 60


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("Reserved1", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def on_ac_power():
    status = SYSTEM_POWER_STATUS()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    return status.ACLineStatus == 1


def main():
    while True:
        if on_ac_power():
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
