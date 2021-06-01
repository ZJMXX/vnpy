import time
from datetime import datetime

from backtest_entrance.setting import Info
from vnpy.app.data_manager import DataManagerApp
from vnpy.app.data_manager.engine import ManagerEngine
from vnpy.event import EventEngine
from vnpy.gateway.binance import BinanceGateway
from vnpy.gateway.binances import BinancesGateway
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.engine import MainEngine

binance_setting = {
    "key": Info.key.value,
    "secret": Info.secret.value,
    "session_number": 3,
    "proxy_host": "127.0.0.1",
    "proxy_port": 10809,
}
binances_setting = {
    "key": Info.key.value,
    "secret": Info.secret.value,
    "会话数": 3,
    "服务器": "REAL",
    "合约模式": "正向",
    "代理地址": "127.0.0.1",
    "代理端口": 10809,
}
symbol_exchange_dict = {
    'btcusdt': Exchange.BINANCE,
    'ethusdt': Exchange.BINANCE,
    'bnbusdt': Exchange.BINANCE,
    'adausdt': Exchange.BINANCE,
    'dogeusdt': Exchange.BINANCE,
    'xrpusdt': Exchange.BINANCE,
    'bchusdt': Exchange.BINANCE,
    'linkusdt': Exchange.BINANCE,
    'ltcusdt': Exchange.BINANCE,
    'xlmusdt': Exchange.BINANCE,
    'etcusdt': Exchange.BINANCE,
    'cocosusdt': Exchange.BINANCE,
    'thetausdt': Exchange.BINANCE,
    'vetusdt': Exchange.BINANCE,
    'eosusdt': Exchange.BINANCE,
    'maticusdt': Exchange.BINANCE,
    'trxusdt': Exchange.BINANCE,
    'xmrusdt': Exchange.BINANCE,
    'neousdt': Exchange.BINANCE,
    'fttusdt': Exchange.BINANCE,
}

event_engine = EventEngine()
main_engine = MainEngine(event_engine)
main_engine.add_gateway(BinanceGateway)
main_engine.add_gateway(BinancesGateway)
main_engine.add_app(DataManagerApp)
main_engine.connect(binance_setting, "BINANCE")
main_engine.connect(binances_setting, "BINANCES")

manager_engine = ManagerEngine(main_engine=main_engine, event_engine=event_engine)
time.sleep(5)
for i in symbol_exchange_dict.items():
    manager_engine.download_bar_data(symbol=i[0], exchange=i[1], interval=Interval.MINUTE.DAILY,
                                     start=datetime(2000, 1, 1, 0, 0, 0))
    print(f'数据下载完成：{i[0]}')
