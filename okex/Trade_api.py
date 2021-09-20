from .client import Client
from .consts import *


class TradeAPI(Client):
    
    def place_order(self, instId, tdMode, side, ordType, sz, ccy=None, clOrdId=None, tag=None, posSide=None, px=None,
                    reduceOnly=None):
        params = {'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': ordType, 'sz': sz, 'ccy': ccy,
                  'clOrdId': clOrdId, 'tag': tag, 'posSide': posSide, 'px': px, 'reduceOnly': reduceOnly}
        return self._request_with_params(POST, PLACR_ORDER, params)

    
