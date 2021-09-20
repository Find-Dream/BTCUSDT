#!/usr/bin/env python
# -*- coding: utf-8 -*-

from tkinter import *
from okex.trade import trade,pos_info,acc_info,select_last
import okex.api as api
import okex.Trade_api as Trade
import time
import json
from okex.log import log
from threading import Thread

LOG_LINE_NUM = 0

class MY_GUI():
    def __init__(self,init_window_name):
        self.init_window_name = init_window_name

    def set_init_window(self):
        self.init_window_name.title("BTCUSDT量化交易执行体 - WWW.BTCUSDT.ORG")
        self.init_window_name.geometry('1068x681+5+5')
        self.log_data_Text = Text(self.init_window_name, width=151, height=40,borderwidth=2, relief="groove") 
        self.log_data_Text.grid(row=1, column=1, rowspan=15, columnspan=10)
        # #按钮
        self.start_button = Button(self.init_window_name, text="开始自动交易", bg="lightblue",width=10,command=self.start) 
        self.start_button.grid(row=500,column=1)
        self.stop_button = Button(self.init_window_name, text="停止自动交易", bg="lightblue",width=10,command=self.stop) 
        self.stop_button.grid(row=500,column=2)
        self.close_button = Button(self.init_window_name, text="关闭程序", bg="lightblue",width=10,command=self.close) 
        self.close_button.grid(row=500,column=3)


        self.web_Text = Text( width=151, height=5)
        self.web_Text.grid(column=1, rowspan=15, columnspan=10)
        self.web_Text.insert(END, "\n\nBTCUSDT量化交易云，官网免费下载：www.btcusdt.org\n\n")
        self.web_Text.configure(state=DISABLED)

    def stop(self):
        global auto
        auto = 0

    def start(self):
        global auto
        auto = 1
    
    def close(self):
        global a
        global auto
        a = 0
        auto = 0
        init_window.destroy()

    #获取当前时间
    def get_current_time(self):
        current_time = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
        return current_time

    #日志动态打印
    def write_log_to_Text(self,logmsg):
        global LOG_LINE_NUM
        current_time = self.get_current_time()
        logmsg_in = str(current_time) +" " + str(logmsg) + "\n"      #换行
        if LOG_LINE_NUM <= 38:
            self.log_data_Text.insert(END, logmsg_in)
            LOG_LINE_NUM = LOG_LINE_NUM + 1
        else:
            self.log_data_Text.delete(1.0,2.0)
            self.log_data_Text.insert(END, logmsg_in)


def main():
    
    nowtime = time.time()
    st = time.localtime(nowtime)
    update = time.strftime('%Y-%m-%d',st)
    filenamedate = time.strftime('%Y%m%d',st)
    logfilename = 'mark_'+ str(filenamedate)

    log(logfilename,'========================【获取基础信息开始】========================')
    ZMJ_PORTAL.write_log_to_Text('========================【获取基础信息开始】========================')

    btcusdt_api_data = api.btcusdt_api()

    log(logfilename,'btcusdt_api_data：'+str(btcusdt_api_data))
    # ZMJ_PORTAL.write_log_to_Text('btcusdt_api_data：'+str(btcusdt_api_data))

    btcusdt_api = btcusdt_api_data['rule']
    log(logfilename,'btcusdt_api'+str(btcusdt_api))
    ZMJ_PORTAL.write_log_to_Text('btcusdt_api'+str(btcusdt_api))

    pos_api = btcusdt_api_data['pos']
    log(logfilename,'pos_api'+str(pos_api))
    ZMJ_PORTAL.write_log_to_Text('pos_api'+str(pos_api))

    pos_okex = {}
    acc_okex = {}
    try:
        acc_api = api.select_acc()
        log(logfilename,'读取本地保存的账户信息'+str(acc_api))
        ZMJ_PORTAL.write_log_to_Text('读取本地保存的账户信息'+str(acc_api))
    except:
        acc_okex['lever'] = 1


    acc_info_data = acc_info()[0]['details']


    for i in acc_info_data:
        if i['ccy'] == 'USDT':
            acc_okex['ccy'] = i['cashBal']
            log(logfilename,'读取接口账户余额'+str(i['cashBal']))
            ZMJ_PORTAL.write_log_to_Text('读取接口账户余额'+str(i['cashBal']))

    for i in pos_info():
        if i['mgnMode'] == 'cross' and i['posSide'] == 'long':
            pos_okex['long'] = i['pos']
            if i['pos'] != '0':
                acc_okex['lever'] = i['lever']
                log(logfilename,'读取接口long账户杠杆倍数：'+str(i['lever']))
                ZMJ_PORTAL.write_log_to_Text('读取接口long账户杠杆倍数：'+str(i['lever']))
            else:
                acc_okex['lever'] = acc_api['lever']
                log(logfilename,'读取本地long账户杠杆倍数：'+str(acc_api['lever']))
                ZMJ_PORTAL.write_log_to_Text('读取本地long账户杠杆倍数：'+str(acc_api['lever']))
        elif i['mgnMode'] == 'cross' and i['posSide'] == 'short':
            pos_okex['short'] = i['pos']
            if i['pos'] != '0':
                acc_okex['lever'] = i['lever']
                log(logfilename,'读取接口short账户杠杆倍数：'+str(i['lever']))
                ZMJ_PORTAL.write_log_to_Text('读取接口short账户杠杆倍数：'+str(i['lever']))
            

    api.set_acc(json.dumps(acc_okex))
    log(logfilename,'写入本地账户信息：'+str(acc_okex))
    ZMJ_PORTAL.write_log_to_Text('写入本地账户信息：'+str(acc_okex))
    last = float(select_last())
    log(logfilename,'读取当前价格：'+str(last))
    ZMJ_PORTAL.write_log_to_Text('读取当前价格：'+str(last))

    max_sz = int(float(acc_okex['ccy']) * float(acc_okex['lever']) / last * 100)
    log(logfilename,'最大交易量：'+str(max_sz))
    ZMJ_PORTAL.write_log_to_Text('最大交易量：'+str(max_sz))

    sz_r = max_sz / 20
    log(logfilename,'交易量系数：'+str(sz_r))
    ZMJ_PORTAL.write_log_to_Text('交易量系数：'+str(sz_r))

    pos_api_id = int(btcusdt_api['id'])
    pos_api_posSide = btcusdt_api['posside']
    pos_api_side = btcusdt_api['side']
    pos_api_sz = int(int(btcusdt_api['sz']) * sz_r)
    pos_api_uptime = int(btcusdt_api['uptime'])
    pos_api_long = int(int(pos_api['long']) * sz_r)
    pos_api_short = int(int(pos_api['short']) * sz_r)

    log(logfilename,'pos_api_long：'+str(pos_api_long)+',pos_api_short:'+str(pos_api_short)+',pos_api_sz:'+str(pos_api_sz))
    ZMJ_PORTAL.write_log_to_Text('pos_api_long：'+str(pos_api_long)+',pos_api_short:'+str(pos_api_short)+',pos_api_sz:'+str(pos_api_sz))
    log(logfilename,'本地仓位信息pos_okex：'+str(pos_okex))
    ZMJ_PORTAL.write_log_to_Text('本地仓位信息pos_okex：'+str(pos_okex))


    try:
        pos_log_done = int(api.pos_log_done())
    except:
        pos_log_done = api.pos_log_done()
    
    log(logfilename,'pos_log_done:'+str(pos_log_done))
    ZMJ_PORTAL.write_log_to_Text('pos_log_done:'+str(pos_log_done))

    log(logfilename,'========================【获取基础信息结束】========================')
    ZMJ_PORTAL.write_log_to_Text('========================【获取基础信息结束】========================')
    log(logfilename,'========================【mark任务开始】========================')
    ZMJ_PORTAL.write_log_to_Text('========================【mark任务开始】========================')
    log(logfilename,'判断pos_log_done_id是否为int型:'+str(type(pos_log_done)))
    ZMJ_PORTAL.write_log_to_Text('判断pos_log_done_id是否为int型:'+str(type(pos_log_done)))
    if isinstance(pos_log_done,int):
        log(logfilename,'pos_log_done_id为int型，判断pos_log_done_id与pos_log_id,pos_api_id:'+str(pos_api_id)+',pos_log_done:'+str(pos_log_done))
        ZMJ_PORTAL.write_log_to_Text('pos_log_done_id为int型，判断pos_log_done_id与pos_log_id,pos_api_id:'+str(pos_api_id)+',pos_log_done:'+str(pos_log_done))
        if pos_api_id > pos_log_done:
            log(logfilename,'API的pos_log_id大于pos_log_done_id，判断API更新时间是否在10秒以内,nowtime:'+str(nowtime)+',pos_api_uptime:'+str(pos_api_uptime))
            ZMJ_PORTAL.write_log_to_Text('API的pos_log_id大于pos_log_done_id，判断API更新时间是否在10秒以内,nowtime:'+str(nowtime)+',pos_api_uptime:'+str(pos_api_uptime))
            if nowtime < (pos_api_uptime + 13):
                log(logfilename,'api更新时间在10秒内，判断api交易方向,pos_api_posSide'+str(pos_api_posSide)+',pos_api_side:'+str(pos_api_side))
                ZMJ_PORTAL.write_log_to_Text('api更新时间在10秒内，判断api交易方向,pos_api_posSide'+str(pos_api_posSide)+',pos_api_side:'+str(pos_api_side))
                if pos_api_posSide == 'long' and pos_api_side == 'buy':
                    log(logfilename,'api交易方向：long-buy，判断当前持仓信息与api是否一致')
                    ZMJ_PORTAL.write_log_to_Text('api交易方向：long-buy，判断当前持仓信息与api是否一致')
                    if int(pos_okex['long']) + int(pos_api_sz) == int(pos_api_long):
                        log(logfilename,'当前持仓信息与api一致，执行交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_long)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('当前持仓信息与api一致，执行交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_long)+',API交易数量：'+str(pos_api_sz))
                        trade_ok = trade(pos_api_side,pos_api_posSide,pos_api_sz,pos_api_id)
                        log(logfilename,'执行结果：'+str(trade_ok))
                        ZMJ_PORTAL.write_log_to_Text('执行结果：'+str(trade_ok))
                    elif int(pos_okex['long']) + int(pos_api_sz) < int(pos_api_long):
                        log(logfilename,'当前持仓信息与api一致，执行交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_long)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('当前持仓信息与api一致，执行交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_long)+',API交易数量：'+str(pos_api_sz))
                        trade_ok = trade(pos_api_side,pos_api_posSide,pos_api_sz,pos_api_id)
                        log(logfilename,'执行结果：'+str(trade_ok))
                        ZMJ_PORTAL.write_log_to_Text('执行结果：'+str(trade_ok))
                    else:
                        log(logfilename,'long仓信息不一致，请将long仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_long)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('long仓信息不一致，请将long仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_long)+',API交易数量：'+str(pos_api_sz))

                elif pos_api_posSide == 'long' and pos_api_side == 'sell':
                    log(logfilename,'api交易方向：long-sell，判断是否符合平仓条件')
                    ZMJ_PORTAL.write_log_to_Text('api交易方向：long-sell，判断是否符合平仓条件')
                    if int(pos_okex['long']) > 0:
                        log(logfilename,'符合平仓条件，当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('符合平仓条件，当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        trade_ok = trade(pos_api_side,pos_api_posSide,int(pos_okex['long']),pos_api_id)
                        log(logfilename,'执行结果：'+str(trade_ok))
                        ZMJ_PORTAL.write_log_to_Text('执行结果：'+str(trade_ok))
                    else:
                        log(logfilename,'long仓信息不一致，请将long仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('long仓信息不一致，请将long仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['long'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))

                elif pos_api_posSide == 'short' and pos_api_side == 'sell':
                    log(logfilename,'api交易方向：short-sell，判断当前持仓信息与api是否一致')
                    ZMJ_PORTAL.write_log_to_Text('api交易方向：short-sell，判断当前持仓信息与api是否一致')
                    if int(pos_okex['short']) + int(pos_api_sz) == int(pos_api_short):
                        log(logfilename,'符合开仓条件，执行交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('符合开仓条件，执行交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        trade_ok = trade(pos_api_side,pos_api_posSide,pos_api_sz,pos_api_id)
                        log(logfilename,'执行结果：'+str(trade_ok))
                        ZMJ_PORTAL.write_log_to_Text('执行结果：'+str(trade_ok))
                    elif int(pos_okex['short']) + int(pos_api_sz) < int(pos_api_short):
                        log(logfilename,'符合开仓条件，执行交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('符合开仓条件，执行交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        trade_ok = trade(pos_api_side,pos_api_posSide,pos_api_sz,pos_api_id)
                        log(logfilename,'执行结果：'+str(trade_ok))
                        ZMJ_PORTAL.write_log_to_Text('执行结果：'+str(trade_ok))
                    else:
                        log(logfilename,'short仓信息不一致，请将short仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('short仓信息不一致，请将short仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))

                elif pos_api_posSide == 'short' and pos_api_side == 'buy':
                    log(logfilename,'api交易方向：short-buy，判断是否符合平仓条件')
                    ZMJ_PORTAL.write_log_to_Text('api交易方向：short-buy，判断是否符合平仓条件')
                    if int(pos_okex['short']) > 0:
                        log(logfilename,'符合平仓条件，当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('符合平仓条件，当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        trade_ok = trade(pos_api_side,pos_api_posSide,pos_okex['short'],pos_api_id)
                        log(logfilename,'执行结果：'+str(trade_ok))
                        ZMJ_PORTAL.write_log_to_Text('执行结果：'+str(trade_ok))
                    else:
                        log(logfilename,'short仓信息不一致，请将short仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
                        ZMJ_PORTAL.write_log_to_Text('short仓信息不一致，请将short仓手动平仓后再进行自动交易,当前持仓：'+str(pos_okex['short'])+',API持仓：'+str(pos_api_short)+',API交易数量：'+str(pos_api_sz))
            else:
                log(logfilename,'api更新时间超过10秒内，已错过最佳交易时间,nowtime:'+str(nowtime)+',pos_api_uptime:'+str(pos_api_uptime))
                ZMJ_PORTAL.write_log_to_Text('api更新时间超过10秒内，已错过最佳交易时间,nowtime:'+str(nowtime)+',pos_api_uptime:'+str(pos_api_uptime))
        else:
            log(logfilename,'API的pos_log_id不大于pos_log_done_id，api无新数据，继续执行监控,pos_api_id:'+str(pos_api_id)+',pos_log_done:'+str(pos_log_done))
            ZMJ_PORTAL.write_log_to_Text('API的pos_log_id不大于pos_log_done_id，api无新数据，继续执行监控,pos_api_id:'+str(pos_api_id)+',pos_log_done:'+str(pos_log_done))
    else:
        log(logfilename,'pos_log_done_id不为int型')
        ZMJ_PORTAL.write_log_to_Text('pos_log_done_id不为int型')
        api.set_pos_log_done(pos_api_id)
    log(logfilename,'========================【mark任务结束】========================')
    ZMJ_PORTAL.write_log_to_Text('========================【mark任务结束】========================')

def formain():
    while a == 1:
        if auto == 1:
            main()
            time.sleep(1)

def closeWindow():
    global a
    global auto
    a = 0
    auto = 0
    init_window.destroy()

init_window = Tk()
init_window.protocol('WM_DELETE_WINDOW', closeWindow)
ZMJ_PORTAL = MY_GUI(init_window)
ZMJ_PORTAL.set_init_window()
a = 1
auto = 0

# 创建线程
thread_01 = Thread(target=formain)
thread_01.start()

init_window.mainloop()
