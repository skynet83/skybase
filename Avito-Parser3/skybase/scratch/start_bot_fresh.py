import sys, os
sys.path.insert(0, 'D:/ins/skybase/Avito-Parser3/skybase')
import avito_api_helper

res_start = avito_api_helper.bot_toggle("start")
print("Start result:", res_start)
