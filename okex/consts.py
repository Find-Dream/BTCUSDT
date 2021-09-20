# http header
API_URL = 'https://www.okex.com'

CONTENT_TYPE = 'Content-Type'
OK_ACCESS_KEY = 'OK-ACCESS-KEY'
OK_ACCESS_SIGN = 'OK-ACCESS-SIGN'
OK_ACCESS_TIMESTAMP = 'OK-ACCESS-TIMESTAMP'
OK_ACCESS_PASSPHRASE = 'OK-ACCESS-PASSPHRASE'

ACEEPT = 'Accept'
COOKIE = 'Cookie'
LOCALE = 'Locale='

APPLICATION_JSON = 'application/json'

GET = "GET"
POST = "POST"

SERVER_TIMESTAMP_URL = '/api/v5/public/time'

# account
POSITION_RISK='/api/v5/account/account-position-risk'
ACCOUNT_INFO = '/api/v5/account/balance'
POSITION_INFO = '/api/v5/account/positions'
BILLS_DETAIL = '/api/v5/account/bills'
BILLS_ARCHIVE = '/api/v5/account/bills-archive'
ACCOUNT_CONFIG = '/api/v5/account/config'
POSITION_MODE = '/api/v5/account/set-position-mode'
SET_LEVERAGE = '/api/v5/account/set-leverage'
MAX_TRADE_SIZE = '/api/v5/account/max-size'
MAX_AVAIL_SIZE = '/api/v5/account/max-avail-size'
ADJUSTMENT_MARGIN = '/api/v5/account/position/margin-balance'
GET_LEVERAGE = '/api/v5/account/leverage-info'
MAX_LOAN = '/api/v5/account/max-loan'
FEE_RATES = '/api/v5/account/trade-fee'
INTEREST_ACCRUED = '/api/v5/account/interest-accrued'
INTEREST_RATE = '/api/v5/account/interest-rate'
SET_GREEKS = '/api/v5/account/set-greeks'
MAX_WITHDRAWAL = '/api/v5/account/max-withdrawal'

# funding
DEPOSIT_ADDRESS = '/api/v5/asset/deposit-address'
GET_BALANCES = '/api/v5/asset/balances'
FUNDS_TRANSFER = '/api/v5/asset/transfer'
WITHDRAWAL_COIN = '/api/v5/asset/withdrawal'
DEPOSIT_HISTORIY = '/api/v5/asset/deposit-history'
WITHDRAWAL_HISTORIY = '/api/v5/asset/withdrawal-history'
CURRENCY_INFO = '/api/v5/asset/currencies'
PURCHASE_REDEMPT = '/api/v5/asset/purchase_redempt'
BILLS_INFO = '/api/v5/asset/bills'

# Market Data
TICKERS_INFO = '/api/v5/market/tickers'
TICKER_INFO = '/api/v5/market/ticker'
INDEX_TICKERS = '/api/v5/market/index-tickers'
ORDER_BOOKS = '/api/v5/market/books'
MARKET_CANDLES = '/api/v5/market/candles'
HISTORY_CANDLES = '/api/v5/market/history-candles'
INDEX_CANSLES = '/api/v5/market/index-candles'
MARKPRICE_CANDLES = '/api/v5/market/mark-price-candles'
MARKET_TRADES = '/api/v5/market/trades'
VOLUMNE = '/api/v5/market/platform-24-volume'
ORACLE = '/api/v5/market/oracle'
TIER = '/api/v5/public/tier'

# Public Data
INSTRUMENT_INFO = '/api/v5/public/instruments'
DELIVERY_EXERCISE = '/api/v5/public/delivery-exercise-history'
OPEN_INTEREST = '/api/v5/public/open-interest'
FUNDING_RATE = '/api/v5/public/funding-rate'
FUNDING_RATE_HISTORY = '/api/v5/public/funding-rate-history'
PRICE_LIMIT = '/api/v5/public/price-limit'
OPT_SUMMARY = '/api/v5/public/opt-summary'
ESTIMATED_PRICE = '/api/v5/public/estimated-price'
DICCOUNT_INTETEST_INFO = '/api/v5/public/discount-rate-interest-free-quota'
SYSTEM_TIME = '/api/v5/public/time'
LIQUIDATION_ORDERS = '/api/v5/public/liquidation-orders'
MARK_PRICE = '/api/v5/public/mark-price'

# TRADE
PLACR_ORDER = '/api/v5/trade/order'
BATCH_ORDERS = '/api/v5/trade/batch-orders'
CANAEL_ORDER = '/api/v5/trade/cancel-order'
CANAEL_BATCH_ORDERS = '/api/v5/trade/cancel-batch-orders'
AMEND_ORDER = '/api/v5/trade/amend-order'
AMEND_BATCH_ORDER = '/api/v5/trade/amend-batch-orders'
CLOSE_POSITION = '/api/v5/trade/close-position'
ORDER_INFO = '/api/v5/trade/order'
ORDERS_PENDING = '/api/v5/trade/orders-pending'
ORDERS_HISTORY = '/api/v5/trade/orders-history'
ORDERS_HISTORY_ARCHIVE = '/api/v5/trade/orders-history-archive'
ORDER_FILLS = '/api/v5/trade/fills'
PLACE_ALGO_ORDER = '/api/v5/trade/order-algo'
CANCEL_ALGOS = '/api/v5/trade/cancel-algos'
ORDERS_ALGO_OENDING = '/api/v5/trade/orders-algo-pending'
ORDERS_ALGO_HISTORY = '/api/v5/trade/orders-algo-history'

# SubAccount
BALANCE = '/api/v5/account/subaccount/balances'
BILLs = '/api/v5/asset/subaccount/bills'
DELETE = '/api/v5/users/subaccount/delete-apikey'
RESET = '/api/v5/users/subaccount/modify-apikey'
CREATE = '/api/v5/users/subaccount/apikey'
VIEW_LIST = '/api/v5/users/subaccount/list'
CONTROL_TRANSFER = '/api/v5/asset/subaccount/transfer'

# status
STATUS = '/api/v5/system/status'
