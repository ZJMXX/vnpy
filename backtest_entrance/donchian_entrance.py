from vnpy.app.cta_strategy.backtesting import BacktestingEngine
from donchian import Donchian
from vnpy.trader.constant import Interval

from datetime import datetime

engine = BacktestingEngine()
engine.set_parameters(vt_symbol='BTCUSDT.BYBIT',
                      interval=Interval.MINUTE.value,
                      start=datetime(2020, 7, 1),
                      end=datetime(2021, 4, 23),
                      rate=0.000025,
                      slippage=0.2,
                      size=5,
                      pricetick=0.01,
                      capital=1000000)

engine.add_strategy(Donchian, {})
engine.load_data()
engine.run_backtesting()
engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()
