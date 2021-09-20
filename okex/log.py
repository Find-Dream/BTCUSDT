# -*- coding: utf-8 -*-
# 写日志
import time

def log(filename,neirong):
    filepath = './log/'+filename+'.log'
    date = time.time() 
    st = time.localtime(date)
    ft = time.strftime('%Y-%m-%d %H:%M:%S', st)
    with open(filepath,"a",encoding='UTF-8') as logfile:
        logs = logfile
        logs.write(ft)
        logs.write('：')
        logs.write(str(neirong))
        logs.write('\n')
        logs.close