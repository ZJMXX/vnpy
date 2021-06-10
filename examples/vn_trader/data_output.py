from datetime import datetime

from vnpy.app.data_manager import DataManagerApp
from vnpy.app.data_manager.engine import ManagerEngine
from vnpy.event import EventEngine
from vnpy.gateway.binance import BinanceGateway
from vnpy.gateway.binances import BinancesGateway
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.engine import MainEngine

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

manager_engine = ManagerEngine(main_engine=main_engine, event_engine=event_engine)
path = 'D:/Work Project/research/Pair Trading/mine/data/'
for i in symbol_exchange_dict.items():
    file = str(i[0])
    file_path = path + file + '.csv'
    manager_engine.output_data_to_csv(file_path=file_path, symbol=i[0], exchange=i[1], interval=Interval.MINUTE,
                                      start=datetime(2019, 1, 1, 0, 0, 0), end=datetime(2099, 12, 31))
    print(f'数据导出到{file_path}完成：{i[0]}')
