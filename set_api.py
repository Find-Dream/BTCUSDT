#!/usr/bin/env python
# -*- coding: utf-8 -*-

from tkinter import *
import json
from threading import Thread

LOG_LINE_NUM = 0

class MY_GUI():
    def __init__(self,init_window_name):
        self.init_window_name = init_window_name


    #设置窗口
    def set_init_window(self):
        self.init_window_name.title("设置API - 量化交易执行体 - WWW.BTCUSDT.ORG")
        self.init_window_name.geometry('550x300+100+100')
        self.init_window_name["bg"] = "#F0F0F0"
        #标签
        self.Key_label = Label(self.init_window_name, width=10, height=1 ,text="Key")
        self.Key_label.grid(row=0, column=0)
        self.Secret_label = Label(self.init_window_name, width=10, height=1 ,text="Secret")
        self.Secret_label.grid(row=50, column=0)
        self.Passphrase_label = Label(self.init_window_name, width=10, height=1 ,text="Passphrase")
        self.Passphrase_label.grid(row=100, column=0)
        self.ok_label = Label(self.init_window_name, width=10, height=1 ,text="交易盘")
        self.ok_label.grid(row=150, column=0)
        #文本框
        self.Key_Text = Entry(self.init_window_name, width=40,borderwidth=2, relief="groove")  #Key
        self.Key_Text.grid(row=0, column=1)
        self.Secret_Text = Entry(self.init_window_name, width=40,borderwidth=2, relief="groove")  #Secret
        self.Secret_Text.grid(row=50, column=1)
        self.Passphrase_Text = Entry(self.init_window_name, width=40,borderwidth=2, relief="groove")  # Passphrase
        self.Passphrase_Text.grid(row=100, column=1)
        self.ok_Text = Entry(self.init_window_name, width=40,borderwidth=2, relief="groove")  # 交易盘
        self.ok_Text.grid(row=150, column=1)
        

        #按钮
        self.save_button = Button(self.init_window_name, text="保存并关闭", bg="lightblue",width=10,command=self.save) 
        self.save_button.grid(column=1)


        self.ok_info_Text = Text( width=80, height=8)
        self.ok_info_Text.grid(column=0, rowspan=15, columnspan=10)
        self.ok_info_Text.insert(END, "交易盘选择：\n0、真实盘\n1、模拟盘\n\nBTCUSDT量化交易云，官网免费下载：www.btcusdt.org")
        self.ok_info_Text.configure(state=DISABLED)

    def save(self):
        Key = self.Key_Text.get()
        Secret = self.Secret_Text.get()
        Passphrase = self.Passphrase_Text.get()
        flag = self.ok_Text.get()
        okex_api = {}
        okex_api['api_key'] = Key
        okex_api['secret_key'] = Secret
        okex_api['passphrase'] = Passphrase
        okex_api['flag'] = flag
        
        api_info = json.dumps(okex_api)
        with open('./okex_api.json','w') as okex_api_info:
            okex_api_info.write(str(api_info))
        init_window.destroy()

    def select_api(self):
        with open('./okex_api.json','r',encoding="utf-8") as okex_api_data:
            okex_api = json.loads(okex_api_data.read())
            self.Key_Text.insert(END, okex_api['api_key'])
            self.Secret_Text.insert(END, okex_api['secret_key'])
            self.Passphrase_Text.insert(END, okex_api['passphrase'])
            self.ok_Text.insert(END, okex_api['flag'])

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
ZMJ_PORTAL.select_api()

init_window.mainloop()
