import requests
import json

def btcusdt_api():
    btcusdt_api_url = "http://api.btcusdt.org"
    return requests.get(btcusdt_api_url).json()

def okex_api():
    with open('./okex_api.json','r',encoding="utf-8") as okex_api_data:
        okex_api = json.loads(okex_api_data.read())
    return okex_api

def pos_log_done():
    with open('./data/pos_log_done.txt','r',encoding="utf-8") as pos_log_done_data:
        pos_log_done = pos_log_done_data.read()
    return pos_log_done

def set_pos_log_done(pos_log_id):
    with open('./data/pos_log_done.txt','w') as set_pos_log_done_data:
        set_pos_log_done_data.write(str(pos_log_id))

def set_acc(acc_info):
    with open('./data/acc.txt','w') as set_acc_data:
        set_acc_data.write(str(acc_info))

def select_acc():
    with open('./data/acc.txt','r',encoding="utf-8") as select_acc_data:
        select_acc = json.loads(select_acc_data.read())
    return select_acc
