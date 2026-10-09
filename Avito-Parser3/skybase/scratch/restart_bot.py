import sys, os
sys.path.insert(0, 'D:/ins/skybase/Avito-Parser3/skybase')
import avito_api_helper

print("Stopping bot...")
res_stop = avito_api_helper.bot_toggle("stop")
print("Stop result:", res_stop)

import time
time.sleep(1)

print("Starting bot...")
res_start = avito_api_helper.bot_toggle("start")
print("Start result:", res_start)
