#!/usr/bin/python


import psutil
p = psutil.Process()
with p.oneshot():
    print(p.name())

# Iterate over all running process
for proc in psutil.process_iter(['pid', 'name']):
    try:
        # Get process name & pid from process object.
        #processName = proc.name()
        #processID = proc.pid
        #print(processName , processID)
        print(proc.info)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

