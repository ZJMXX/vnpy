import time
from datetime import datetime

from backtest_entrance.setting import Info
from vnpy.app.data_manager import DataManagerApp
from vnpy.app.data_manager.engine import ManagerEngine
from vnpy.event import EventEngine
from vnpy.gateway.binance import BinanceGateway
from vnpy.gateway.binances import BinancesGateway
from vnpy.trader.constant import Exchange
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
symbol = 'eosusdt'
exchange = Exchange.BINANCE

event_engine = EventEngine()
main_engine = MainEngine(event_engine)
main_engine.add_gateway(BinanceGateway)
main_engine.add_gateway(BinancesGateway)
main_engine.add_app(DataManagerApp)
main_engine.connect(binance_setting, "BINANCE")
main_engine.connect(binances_setting, "BINANCES")

manager_engine = ManagerEngine(main_engine=main_engine, event_engine=event_engine)
time.sleep(3)
manager_engine.download_bar_data(symbol=symbol, exchange=exchange, interval='1m', start=datetime(2021, 5, 28, 0, 0, 0))
print('数据下载完成')
