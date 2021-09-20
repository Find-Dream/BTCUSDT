import okex.api as api
import okex.Account_api as Account
import okex.Market_api as Market
import okex.Trade_api as Trade
import json
from okex.log import log
import time

def trade(pos_api_side,pos_api_posSide,pos_api_sz,pos_api_id):
    nowtime = time.time()
    st = time.localtime(nowtime)
    filenamedate = time.strftime('%Y%m%d',st)
    logfilename = 'err_'+ str(filenamedate)
    okex_api = api.okex_api()
    api_key = okex_api['api_key']
    secret_key = okex_api['secret_key']
    passphrase = okex_api['passphrase']
    flag = okex_api['flag'] 

    tradeAPI = Trade.TradeAPI(api_key, secret_key, passphrase, False, flag)
    result = tradeAPI.place_order(instId='BTC-USDT-SWAP', tdMode='cross', side=pos_api_side,posSide=pos_api_posSide,ordType='market', sz=pos_api_sz)
    api.set_pos_log_done(pos_api_id)
    
    if result['code'] == '0' :
        api.set_pos_log_done(pos_api_id)
        return json.dumps(result)

    else:
        log(logfilename,result)
        return json.dumps(result)

    

def pos_info():
    nowtime = time.time()
    st = time.localtime(nowtime)
    filenamedate = time.strftime('%Y%m%d',st)
    logfilename = 'err_'+ str(filenamedate)

    okex_api = api.okex_api()
    api_key = okex_api['api_key']
    secret_key = okex_api['secret_key']
    passphrase = okex_api['passphrase']
    flag = okex_api['flag'] 
    accountAPI = Account.AccountAPI(api_key, secret_key, passphrase, False, flag)
    result = accountAPI.get_positions('SWAP', 'BTC-USDT-SWAP')

    if result['code'] == '0':
        return result['data']
    else:
        log(logfilename,result)
        return result

def acc_info():
    nowtime = time.time()
    st = time.localtime(nowtime)
    filenamedate = time.strftime('%Y%m%d',st)
    logfilename = 'err_'+ str(filenamedate)

    okex_api = api.okex_api()
    api_key = okex_api['api_key']
    secret_key = okex_api['secret_key']
    passphrase = okex_api['passphrase']
    flag = okex_api['flag'] 
    accountAPI = Account.AccountAPI(api_key, secret_key, passphrase, False, flag)
    result = accountAPI.get_account()

    if result['code'] == '0':
        return result['data']
    else:
        log(logfilename,result)
        return result

def select_last():
    okex_api = api.okex_api()
    api_key = okex_api['api_key']
    secret_key = okex_api['secret_key']
    passphrase = okex_api['passphrase']
    flag = okex_api['flag'] 
    marketAPI = Market.MarketAPI(api_key, secret_key, passphrase, False, flag)
    result = marketAPI.get_ticker('BTC-USDT-SWAP')

    return result['data'][0]['last']
