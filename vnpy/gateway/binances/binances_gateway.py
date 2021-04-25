"""
Gateway for Binance Crypto Exchange.
"""

import urllib
import hashlib
import hmac
import time
from copy import copy
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Dict, List, Tuple
import pytz
import requests


from vnpy.api.rest import RestClient, Request
from vnpy.api.websocket import WebsocketClient
from vnpy.trader.constant import (
    BinanceContractType, Direction,
    Exchange,
    Product,
    Status,
    OrderType,
    Interval,
    Offset
)
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    TickData,
    OrderData,
    TradeData,
    AccountData,
    BinanceContractData,
    PositionData,
    BarData,
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest
)
from vnpy.trader.event import EVENT_TIMER
from vnpy.event import Event, EventEngine

F_REST_HOST: str = "https://fapi.binance.com"
F_WEBSOCKET_TRADE_HOST: str = "wss://fstream.binance.com/ws/"
F_WEBSOCKET_DATA_HOST: str = "wss://fstream.binance.com/stream?streams="

F_TESTNET_RESTT_HOST: str = "https://testnet.binancefuture.com"
F_TESTNET_WEBSOCKET_TRADE_HOST: str = "wss://stream.binancefuture.com/ws/"
F_TESTNET_WEBSOCKET_DATA_HOST: str = "wss://stream.binancefuture.com/stream?streams="

D_REST_HOST: str = "https://dapi.binance.com"
D_WEBSOCKET_TRADE_HOST: str = "wss://dstream.binance.com/ws/"
D_WEBSOCKET_DATA_HOST: str = "wss://dstream.binance.com/stream?streams="

D_TESTNET_RESTT_HOST: str = "https://testnet.binancefuture.com"
D_TESTNET_WEBSOCKET_TRADE_HOST: str = "wss://dstream.binancefuture.com/ws/"
D_TESTNET_WEBSOCKET_DATA_HOST: str = "wss://dstream.binancefuture.com/stream?streams="

STATUS_BINANCES2VT: Dict[str, Status] = {
    "NEW": Status.NOTTRADED,
    "PARTIALLY_FILLED": Status.PARTTRADED,
    "FILLED": Status.ALLTRADED,
    "CANCELED": Status.CANCELLED,
    "REJECTED": Status.REJECTED,
    "EXPIRED": Status.CANCELLED
}

ORDERTYPE_VT2BINANCES: Dict[OrderType, Tuple[str, str]] = {
    OrderType.LIMIT: ("LIMIT", "GTC"),
    OrderType.MARKET: ("MARKET", "GTC"),
    OrderType.FAK: ("LIMIT", "IOC"),
    OrderType.FOK: ("LIMIT", "GTX"),
    OrderType.TAKE_PROFIT_MARKET: ("TAKE_PROFIT_MARKET", "GTC"),
    OrderType.TAKE_PROFIT: ("TAKE_PROFIT", "GTC"),
    OrderType.STOP_LOSS: ("STOP_LOSS", "GTC"),
    OrderType.STOP_LOSS_LIMIT: ("STOP_LOSS_LIMIT", "GTC"),
    OrderType.STOP: ("STOP", "GTC")
}

ORDERTYPE_BINANCES2VT: Dict[Tuple[str, str], OrderType] = {v: k for k, v in ORDERTYPE_VT2BINANCES.items()}

SIDE_VT2BINANCEF: Dict[Direction, str] = {
    Direction.LONG: "LONG",
    Direction.SHORT: "SHORT"
}
SIDE_BINACES2VT: Dict[str, Direction] = {v: k for k, v in SIDE_VT2BINANCEF.items()}

DIRECTION_VT2BINANCES: Dict[Direction, str] = {
    Direction.LONG: "BUY",
    Direction.SHORT: "SELL"
}
DIRECTION_BINANCES2VT: Dict[str, Direction] = {v: k for k, v in DIRECTION_VT2BINANCES.items()}

OFFSET_VT2BINANCES: Dict[Offset, bool] = {
    Offset.OPEN: False,
    Offset.CLOSE: True
}
OFFSET_BINANCES2VT: Dict[bool, Offset] = {v: k for k, v in OFFSET_VT2BINANCES.items()}

INTERVAL_VT2BINANCES: Dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.HOUR: "1h",
    Interval.DAILY: "1d",
}

TIMEDELTA_MAP: Dict[Interval, timedelta] = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta(days=1),
}

ContractType_VT2BINANCES: Dict[BinanceContractType, str] = {
    BinanceContractType.PERPETUAL: "PERPETUAL",
    BinanceContractType.CURRENT_MONTH: "CURRENT_MONTH",
    BinanceContractType.NEXT_MONTH: "NEXT_MONTH",
    BinanceContractType.CURRENT_QUARTER: "CURRENT_QUARTER",
    BinanceContractType.NEXT_QUARTER: "NEXT_QUARTER",
    BinanceContractType.CURRENT_QUARTER_DELIVERING: "CURRENT_QUARTER DELIVERING",
    BinanceContractType.NEXT_QUARTER_DELIVERING: "NEXT_QUARTER DELIVERING",
    BinanceContractType.CURRENT_MONTH_DELIVERING: "CURRENT_MONTH DELIVERING",
    BinanceContractType.NEXT_MONTH_DELIVERING: "NEXT_MONTH DELIVERING"
}
ContractType_BINANCES2VT: Dict[str, BinanceContractType] = {v: k for k, v in ContractType_VT2BINANCES.items()}

CHINA_TZ = pytz.timezone("Asia/Shanghai")


class Security(Enum):
    NONE: int = 0
    SIGNED: int = 1
    API_KEY: int = 2


symbol_name_map: Dict[str, str] = {}
contract_type_map: Dict[str, BinanceContractType] = {}
margin_asset_map: Dict[str, str] = {}
last_price_map: Dict[str, float] = {}


class BinancesGateway(BaseGateway):
    """
    VN Trader Gateway for Binance connection.
    """

    default_setting = {
        "key": "",
        "secret": "",
        "会话数": 3,
        "服务器": ["TESTNET", "REAL"],
        "合约模式": ["反向", "正向"],
        "代理地址": "",
        "代理端口": 0,
    }

    exchanges: Exchange = [Exchange.BINANCE]

    def __init__(self, event_engine: EventEngine):
        """Constructor"""
        super().__init__(event_engine, "BINANCES")
        self.count = 0

        self.trade_ws_api = BinancesTradeWebsocketApi(self)
        self.market_ws_api = BinancesDataWebsocketApi(self)
        self.rest_api = BinancesRestApi(self)

    def connect(self, setting: dict) -> None:
        """"""
        key = setting["key"]
        secret = setting["secret"]
        session_number = setting["会话数"]
        server = setting["服务器"]
        proxy_host = setting["代理地址"]
        proxy_port = setting["代理端口"]

        if setting["合约模式"] == "正向":
            usdt_base = True
        else:
            usdt_base = False

        self.rest_api.connect(usdt_base, key, secret, session_number, server,
                              proxy_host, proxy_port)
        self.market_ws_api.connect(usdt_base, proxy_host, proxy_port, server)

        self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def subscribe(self, req: SubscribeRequest) -> None:
        """"""
        self.market_ws_api.subscribe(req)

    def send_order(self, req: OrderRequest) -> str:
        """"""
        return self.rest_api.send_order(req)

    def cancel_order(self, req: CancelRequest) -> Request:
        """"""
        return self.rest_api.cancel_order(req)

    def query_order(self, req: CancelRequest) -> Request:
        """"""
        return self.rest_api.query_order_exits(req)

    def query_leverage(self, symbol):
        """
        查询最大杠杆倍数
        """
        return self.rest_api.query_leverage(symbol)

    def query_account(self) -> None:
        """"""
        pass

    def query_position(self) -> None:
        """"""
        pass

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """"""
        return self.rest_api.query_history(req)

    def close(self) -> None:
        """"""
        self.rest_api.stop()
        self.trade_ws_api.stop()
        self.market_ws_api.stop()

    def process_timer_event(self, event: Event) -> None:
        """"""
        self.rest_api.keep_user_stream()
        if self.status.get('td_con', False) \
                and self.status.get('tdws_con', False) \
                and self.status.get('mdws_con', False):
            self.status.update({'con': True})

        self.count += 1
        if self.count < 2:
            return
        self.count = 0
        if len(self.query_functions) > 0:
            func = self.query_functions.pop(0)
            func()
            self.query_functions.append(func)


class BinancesRestApi(RestClient):
    """
    BINANCE REST API
    """

    def __init__(self, gateway: BinancesGateway):
        """"""
        super().__init__()

        self.gateway: BinancesGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.trade_ws_api: BinancesTradeWebsocketApi = self.gateway.trade_ws_api

        self.key: str = ""
        self.secret: str = ""

        self.user_stream_key: str = ""
        self.keep_alive_count: int = 0
        self.recv_window: int = 5000
        self.time_offset: int = 0

        self.contracts = {}

        self.order_count: int = 1_000_000
        self.order_count_lock: Lock = Lock()
        self.connect_time: int = 0
        self.usdt_base: bool = False
        self.cache_position_symbols = {}
        self.accountid = ""

        self.dualSidePosition = False

    def sign(self, request: Request) -> Request:
        """
        Generate BINANCE signature.
        """
        security = request.data["security"]
        if security == Security.NONE:
            request.data = None
            return request

        if request.params:
            path = request.path + "?" + urllib.parse.urlencode(request.params)
        else:
            request.params = dict()
            path = request.path

        if security == Security.SIGNED:
            timestamp = int(time.time() * 1000)

            if self.time_offset > 0:
                timestamp -= abs(self.time_offset)
            elif self.time_offset < 0:
                timestamp += abs(self.time_offset)

            request.params["timestamp"] = timestamp

            query = urllib.parse.urlencode(sorted(request.params.items()))
            signature = hmac.new(self.secret, query.encode(
                "utf-8"), hashlib.sha256).hexdigest()

            query += "&signature={}".format(signature)
            path = request.path + "?" + query

        request.path = path
        request.params = {}
        request.data = {}

        # Add headers
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-MBX-APIKEY": self.key
        }

        if security in [Security.SIGNED, Security.API_KEY]:
            request.headers = headers

        return request

    def connect(
            self,
            usdt_base: bool,
            key: str,
            secret: str,
            session_number: int,
            server: str,
            proxy_host: str,
            proxy_port: int
    ) -> None:
        """
        Initialize connection to REST server.
        """
        self.usdt_base = usdt_base
        self.key = key
        self.secret = secret.encode()
        self.proxy_port = proxy_port
        self.proxy_host = proxy_host
        self.server = server
        self.pairs: list = []
        self.trade_symbol: list = []

        self.connect_time = (
                int(datetime.now().strftime("%y%m%d%H%M%S")) * self.order_count
        )

        if self.server == "REAL":
            if self.usdt_base:
                self.init(F_REST_HOST, proxy_host, proxy_port)
            else:
                self.init(D_REST_HOST, proxy_host, proxy_port)
        else:
            if self.usdt_base:
                self.init(F_TESTNET_RESTT_HOST, proxy_host, proxy_port)
            else:
                self.init(D_TESTNET_RESTT_HOST, proxy_host, proxy_port)

        self.start(session_number)

        self.gateway.write_log("REST API启动成功")
        self.gateway.status.update({'td_con': True, 'td_con_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        if self.gateway.status.get('md_con', False):
            self.gateway.status.update({'con': True})

        self.query_time()
        self.query_account()
        self.query_contract()
        self.query_position()
        self.query_order()
        # self.query_trade()
        self.start_user_stream()
        self.query_dual()

        # 添加到定时查询队列中
        self.gateway.query_functions = [self.query_account, self.query_position]

    def query_time(self) -> Request:
        """"""
        data = {
            "security": Security.NONE
        }

        if self.usdt_base:
            path = "/fapi/v1/time"
        else:
            path = "/dapi/v1/time"

        return self.add_request(
            "GET",
            path,
            callback=self.on_query_time,
            on_error=self.on_default_error,
            data=data
        )

    def query_account(self) -> Request:
        """"""
        data = {"security": Security.SIGNED}

        if self.usdt_base:
            path = "/fapi/v2/account"
        else:
            path = "/dapi/v1/account"

        params = {
            "recvWindow": 20000
        }

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_account,
            on_error=self.on_default_error,
            data=data,
            params=params
        )

    def query_dual(self):
        """
        查询持仓方向
        """
        data = {"security": Security.SIGNED}

        if self.usdt_base:
            path = "/fapi/v1/positionSide/dual"
        else:
            path = "/dapi/v1/positionSide/dual"

        params = {
            "recvWindow": 200000
        }

        resp = self.request(
            method="GET",
            path=path,
            data=data,
            params=params
        )
        if isinstance(resp, requests.Response):
            if resp.status_code // 100 != 2:
                msg = f"查询持仓方向失败，状态码：{resp.status_code}，信息：{resp.text}"
                self.gateway.write_log(msg)
            else:
                data = resp.json()
                if data['dualSidePosition']:
                    self.dualSidePosition = True
        else:
            msg = f"查询持仓方向失败，委托下单失败"
            self.gateway.write_log(msg)
            time.sleep(3)
            self.query_dual()

        pass

    def query_position(self) -> Request:
        """"""
        data = {"security": Security.SIGNED}

        if self.usdt_base:
            path = "/fapi/v2/positionRisk"
        else:
            path = "/dapi/v1/positionRisk"

        params = {
            "recvWindow": 20000
        }

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_position,
            on_error=self.on_default_error,
            data=data,
            params=params
        )

    def query_order(self) -> Request:
        """"""
        data = {"security": Security.SIGNED}

        if self.usdt_base:
            path = "/fapi/v1/openOrders"
        else:
            path = "/dapi/v1/openOrders"

        params = {
            "recvWindow": 20000
        }

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_order,
            on_error=self.on_default_error,
            data=data,
            params=params
        )

    def query_contract(self) -> Request:
        """"""
        data = {
            "security": Security.NONE
        }

        if self.usdt_base:
            path = "/fapi/v1/exchangeInfo"
        else:
            path = "/dapi/v1/exchangeInfo"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_contract,
            on_error=self.on_default_error,
            data=data
        )

    def _new_order_id(self) -> int:
        """"""
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    def send_order(self, req: OrderRequest) -> str:
        """"""
        orderid = "328hhn6c-" + str(self.connect_time + self._new_order_id())
        order = req.create_order_data(
            orderid,
            self.gateway_name
        )
        self.gateway.on_order(order)

        data = {
            "security": Security.SIGNED
        }

        order_type, time_condition = ORDERTYPE_VT2BINANCES[req.type]

        params = {
            "symbol": req.symbol,
            "side": DIRECTION_VT2BINANCES[req.direction],
            "type": order_type,
            "timeInForce": time_condition,
            "price": float(req.price),
            "quantity": float(req.volume),
            "newClientOrderId": orderid,
            "recvWindow": 20000
        }

        if self.dualSidePosition:
            if req.offset == Offset.OPEN:
                positionSide = SIDE_VT2BINANCEF[req.direction]
            else:
                if req.direction == Direction.LONG:
                    positionSide = SIDE_VT2BINANCEF[Direction.SHORT]
                else:
                    positionSide = SIDE_VT2BINANCEF[Direction.LONG]
            params['positionSide'] = positionSide

        if order_type == "STOP":
            params['stopPrice'] = float(req.price)

        if order_type == "MARKET":
            params.pop('price', None)
            params.pop('timeInForce', None)

        # if req.offset == Offset.CLOSE:
        #     params["reduceOnly"] = True

        if self.usdt_base:
            path = "/fapi/v1/order"
        else:
            path = "/dapi/v1/order"

        resp = self.request(
            method="POST",
            path=path,
            data=data,
            params=params
        )

        if isinstance(resp, requests.Response):
            if resp.status_code // 100 != 2:
                if resp.status_code in [502, 504]:
                    msg = f"委托下单失败，状态码：{resp.status_code}，信息：{req.symbol}, {orderid}"
                    self.gateway.write_log(msg)
                    return self.send_order(req)
                msg = f"委托下单失败，状态码：{resp.status_code}，信息：{resp.text}, {req.symbol}, {orderid}"
                self.gateway.write_log(msg)
                data = resp.json()
                if data['code'] == -2021:
                    req.type = OrderType.LIMIT
                    return self.send_order(req)
                else:
                    return False
            else:
                return order.vt_orderid
        else:
            msg = f"网络连接失败，委托下单失败。{req.symbol} {orderid}"
            self.gateway.write_log(msg)
            return self.send_order(req)

    def query_trade(self) -> Request:
        """"""
        data = {"security": Security.SIGNED}
        if self.usdt_base:
            path = "/fapi/v1/userTrades"
        else:
            path = "/dapi/v1/userTrades"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_trade,
            data=data,
            on_error=self.on_default_error,
        )

    def query_order_exits(self, req: CancelRequest):
        """
        查询委托是否成功
        """
        data = {
            "security": Security.SIGNED
        }

        params = {
            "symbol": req.symbol,
            "origClientOrderId": req.orderid,
            "recvWindow": 20000
        }

        if self.usdt_base:
            path = "/fapi/v1/openOrder"
        else:
            path = "/dapi/v1/openOrder"

        resp = self.request(
            method="DELETE",
            path=path,
            params=params,
            data=data,
        )

        if isinstance(resp, requests.Response):
            if resp.status_code // 100 != 2:
                msg = f"委托查询失败，状态码：{resp.status_code}，信息：{resp.text}, {req.symbol}, {req.orderid}"
                self.gateway.write_log(msg)
                return False
            else:
                return True
        else:
            msg = f"网络连接失败，取消委托失败"
            self.gateway.write_log(msg)
            return self.query_order_exits(req)

    def query_leverage(self, symbol):
        """
        查询最大杠杆倍数
        """
        data = {
            "security": Security.NONE
        }

        params = {
            "symbol": symbol
        }

        if self.usdt_base:
            path = "/fapi/v1/order"
        else:
            path = "/dapi/v1/order"

        resp = self.request(
            method="GET",
            path=path,
            params=params,
            data=data,
        )

        if isinstance(resp, requests.Response):
            if resp.status_code // 100 != 2:
                msg = f"查询最大杠杆倍数失败，状态码：{resp.status_code}，信息：{resp.text}"
                self.gateway.write_log(msg)
                return False
            else:
                data = resp.json()
                return data['brackets'][0]['initialLeverage']
        else:
            msg = f"网络连接失败，查询最大杠杆倍数"
            self.gateway.write_log(msg)
            return self.query_leverage(symbol)
        pass

    def cancel_order(self, req: CancelRequest) -> Request:
        """
        取消委托
        """
        data = {
            "security": Security.SIGNED
        }

        params = {
            "symbol": req.symbol,
            "origClientOrderId": req.orderid,
            "recvWindow": 20000
        }

        if self.usdt_base:
            path = "/fapi/v1/order"
        else:
            path = "/dapi/v1/order"

        resp = self.request(
            method="DELETE",
            path=path,
            params=params,
            data=data,
        )

        if isinstance(resp, requests.Response):
            if resp.status_code // 100 != 2:
                msg = f"取消委托失败，状态码：{resp.status_code}，信息：{resp.text}, {req.symbol}, {req.orderid}"
                self.gateway.write_log(msg)
                return False
            else:
                return True
        else:
            msg = f"网络连接失败，取消委托失败"
            self.gateway.write_log(msg)
            return self.cancel_order(req)

    def on_default_error(
            self, exception_type: type, exception_value: Exception, tb, request: Request
    ):
        """
        Callback when cancelling order failed on server.
        """
        # Record exception if not ConnectionError
        if not issubclass(exception_type, ConnectionError) and not issubclass(exception_type, ConnectionResetError):
            self.on_error(exception_type, exception_value, tb, request)

    def start_user_stream(self) -> Request:
        """"""
        data = {
            "security": Security.API_KEY
        }

        if self.usdt_base:
            path = "/fapi/v1/listenKey"
        else:
            path = "/dapi/v1/listenKey"

        self.add_request(
            method="POST",
            path=path,
            callback=self.on_start_user_stream,
            on_error=self.on_default_error,
            data=data
        )

    def keep_user_stream(self) -> Request:
        """"""
        self.keep_alive_count += 1
        if self.keep_alive_count < 600:
            return
        self.keep_alive_count = 0

        data = {
            "security": Security.API_KEY
        }

        params = {
            "listenKey": self.user_stream_key
        }

        if self.usdt_base:
            path = "/fapi/v1/listenKey"
        else:
            path = "/dapi/v1/listenKey"
        self.add_request(
            method="PUT",
            path=path,
            callback=self.on_keep_user_stream,
            on_error=self.on_default_error,
            params=params,
            data=data
        )

    def stop(self) -> None:
        return super().stop()

    def on_query_time(self, data: dict, request: Request) -> None:
        """"""
        local_time = int(time.time() * 1000)
        server_time = int(data["serverTime"])
        self.time_offset = local_time - server_time

    def on_query_account(self, data: dict, request: Request) -> None:
        """"""
        if not self.accountid:
            self.accountid = f"{self.gateway_name}_USDT"
        for asset in data["assets"]:
            account = AccountData(
                accountid=asset["asset"],
                balance=float(asset["walletBalance"]),
                frozen=float(asset["maintMargin"]),
                gateway_name=self.gateway_name
            )
            self.pairs.append(asset["asset"])

            if account.balance:
                self.gateway.on_account(account)

        # 临时缓存合约的配置信息
        for position in data["positions"]:
            symbol = position.get('symbol')
            if symbol:
                # if symbol not in self.contracts:
                #     self.gateway.write_log(json.dumps(position, indent=2))
                self.contracts.update({symbol: position})

        # self.gateway.write_log("账户资金查询成功")

    def on_query_position(self, data: dict, request: Request) -> None:
        """"""
        for d in data:
            if d['positionSide'] == "BOTH":
                direction = Direction.LONG if float(d["positionAmt"]) > 0 else Direction.SHORT
            else:
                direction = SIDE_BINACES2VT[d["positionSide"]]
            position = PositionData(
                symbol=d["symbol"],
                exchange=Exchange.BINANCE,
                direction=direction,
                volume=float(d["positionAmt"]),
                price=float(d["entryPrice"]),
                pnl=float(d["unRealizedProfit"]),
                gateway_name=self.gateway_name,
            )

            if position.direction not in [Direction.LONG, Direction.SHORT]:
                continue

            # 如果持仓数量为0，且不在之前缓存过的合约信息中，不做on_position
            key = position.symbol + position.direction.value
            if position.volume == 0:
                if key not in self.cache_position_symbols:
                    continue
            else:
                if key not in self.cache_position_symbols:
                    self.cache_position_symbols.update({key: position.volume})

            if margin_asset_map[position.symbol] != "USDT" and position.symbol in last_price_map.keys():
                position.pnl = position.pnl * last_price_map[position.symbol]

            self.gateway.on_position(position)

        # self.gateway.write_log("持仓信息查询成功")

    def on_query_order(self, data: dict, request: Request) -> None:
        """"""
        for d in data:
            key = (d["type"], d["timeInForce"])
            order_type = ORDERTYPE_BINANCES2VT.get(key, None)
            if not order_type:
                continue

            order = OrderData(
                orderid=d["clientOrderId"],
                symbol=d["symbol"],
                exchange=Exchange.BINANCE,
                price=float(d["price"]),
                volume=float(d["origQty"]),
                type=order_type,
                direction=DIRECTION_BINANCES2VT[d["side"]],
                traded=float(d["executedQty"]),
                status=STATUS_BINANCES2VT.get(d["status"], None),
                datetime=generate_datetime(d["time"]),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_order(order)

        self.gateway.write_log("委托信息查询成功")

    def on_query_trade(self, data: dict, request: Request) -> None:
        """"""
        for d in data:
            dt = datetime.fromtimestamp(d["time"] / 1000)
            time = dt.strftime("%Y-%m-%d %H:%M:%S")

            trade = TradeData(
                accountid=self.accountid,
                symbol=d['symbol'],
                exchange=Exchange.BINANCE,
                orderid=d['orderId'],
                tradeid=d["id"],
                direction=Direction.SHORT if d['side'] == 'SELL' else Direction.LONG,
                offset=Offset.CLOSE if d['buyer'] else Offset.OPEN,
                price=float(d["price"]),
                volume=float(d['qty']),
                time=time,
                datetime=dt,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_trade(trade)

        self.gateway.write_log("委托信息查询成功")

    def on_query_contract(self, data: dict, request: Request) -> None:
        """"""
        for d in data["symbols"]:
            base_currency = d["baseAsset"]
            quote_currency = d["quoteAsset"]
            name = f"{base_currency.upper()}/{quote_currency.upper()}"

            pricetick = 1
            min_volume = 1
            symbol = d["symbol"]

            for f in d["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    pricetick = float(f["tickSize"])
                elif f["filterType"] == "LOT_SIZE":
                    min_volume = float(f["stepSize"])

            # 合约乘数
            symbol_size = 20  # 缺省为20倍的杠杆
            contract_info = self.contracts.get(symbol, {})
            if contract_info:
                symbol_size = int(contract_info.get('leverage', symbol_size))

            contract_type = d['contractType']

            contract = BinanceContractData(
                symbol=symbol,
                exchange=Exchange.BINANCE,
                name=name,
                pricetick=pricetick,
                size=symbol_size,
                min_volume=min_volume,
                margin_rate=1,
                product=Product.FUTURES,
                history_data=True,
                gateway_name=self.gateway_name,
                stop_supported=True,
                market_supported=True,
                margin_asset=d['marginAsset']
            )
            if contract_type:
                contract.contract_type = ContractType_BINANCES2VT[contract_type]
            self.gateway.on_contract(contract)

            symbol_name_map[contract.symbol] = contract.name
            contract_type_map[contract.symbol] = contract.contract_type
            margin_asset_map[contract.symbol] = contract.margin_asset

        self.gateway.write_log("合约信息查询成功")

    def on_start_user_stream(self, data: dict, request: Request) -> None:
        """"""
        self.user_stream_key = data["listenKey"]
        self.keep_alive_count = 0

        if self.server == "REAL":
            url = F_WEBSOCKET_TRADE_HOST + self.user_stream_key
            if not self.usdt_base:
                url = D_WEBSOCKET_TRADE_HOST + self.user_stream_key
        else:
            url = F_TESTNET_WEBSOCKET_TRADE_HOST + self.user_stream_key
            if not self.usdt_base:
                url = D_TESTNET_WEBSOCKET_TRADE_HOST + self.user_stream_key

        self.trade_ws_api.connect(url, self.proxy_host, self.proxy_port)

    def on_keep_user_stream(self, data: dict, request: Request) -> None:
        """"""
        pass

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """"""
        history = []
        limit = 1000
        start_time = int(datetime.timestamp(req.start))

        while True:
            # Create query params
            params = {
                "symbol": req.symbol,
                "interval": INTERVAL_VT2BINANCES[req.interval],
                "limit": limit,
                "startTime": start_time * 1000,  # convert to millisecond
            }

            # Add end time if specified
            if req.end:
                end_time = int(datetime.timestamp(req.end))
                if start_time > end_time:
                    break
                params["endTime"] = end_time * 1000  # convert to millisecond

            # Get response from server
            if self.usdt_base:
                path = "/fapi/v1/klines"
            else:
                path = "/dapi/v1/klines"

            contract_type = contract_type_map[req.symbol]
            if contract_type == BinanceContractType.CURRENT_QUARTER:
                path = "/dapi/v1/continuousKlines"
                params['contractType'] = "CURRENT_QUARTER"
                params.pop("symbol", None)
                symbol = req.symbol.split("_")[0]
                params['pair'] = symbol
                params['endTime'] = params.pop("startTime")

            elif contract_type == BinanceContractType.NEXT_QUARTER:
                path = "/dapi/v1/continuousKlines"
                params['contractType'] = "NEXT_QUARTER"
                params.pop("symbol", None)
                symbol = req.symbol.split("_")[0]
                params['pair'] = symbol
                params['endTime'] = params.pop("startTime")

            elif not self.usdt_base:
                params['endTime'] = params.pop("startTime")

            resp = self.request(
                "GET",
                path=path,
                data={"security": Security.NONE},
                params=params
            )

            if isinstance(resp, requests.Response):
                # Break if request failed with other status code
                if resp.status_code // 100 != 2:
                    msg = f"获取历史数据失败，状态码：{resp.status_code}，信息：{resp.text}"
                    self.gateway.write_log(msg)
                    break
                else:
                    data = resp.json()
                    if not data:
                        msg = f"获取历史数据为空，开始时间：{start_time}"
                        self.gateway.write_log(msg)
                        break

                    buf = []
                    end_timestamp = 0

                    for l in data:
                        bar = BarData(
                            symbol=req.symbol,
                            exchange=req.exchange,
                            datetime=generate_datetime(l[0]),
                            interval=req.interval,
                            volume=float(l[5]),
                            open_price=float(l[1]),
                            high_price=float(l[2]),
                            low_price=float(l[3]),
                            close_price=float(l[4]),
                            gateway_name=self.gateway_name
                        )
                        buf.append(bar)
                        end_timestamp = l[0]

                    history.extend(buf)

                    begin = buf[0].datetime
                    end = buf[-1].datetime
                    msg = f"获取历史数据成功，{req.symbol} - {req.interval.value}，{begin} - {end}"
                    self.gateway.write_log(msg)

                    # Break if total data count less than limit (latest date collected)
                    if len(data) < limit:
                        break

                    # Update start time
                    bar = buf[-1]
                    # start_dt = bar.datetime + TIMEDELTA_MAP[req.interval]
                    # start_time = int(datetime.timestamp(start_dt))
                    time_delta_stamp = 60
                    if req.interval == Interval.HOUR:
                        time_delta_stamp = 60 * 60
                    elif req.interval == Interval.DAILY:
                        time_delta_stamp = 60 * 60 * 24

                    start_time = int(end_timestamp / 1000) + time_delta_stamp
                    if contract_type == BinanceContractType.NEXT_QUARTER or contract_type == BinanceContractType.CURRENT_QUARTER or not self.usdt_base:
                        if int(datetime.timestamp(req.end)) - start_time > time_delta_stamp * 999:
                            start_time += time_delta_stamp * 999
                        else:
                            limit = int((int(datetime.timestamp(req.end)) - start_time) / time_delta_stamp)
                            start_time += int(datetime.timestamp(req.end)) - start_time - time_delta_stamp
                            if limit == 0:
                                break
                            else:
                                limit += 20
                    if start_time > int(datetime.timestamp(req.end)):
                        print("开始时间大于结束时间")
                        break
            else:
                pass

        return history


class BinancesTradeWebsocketApi(WebsocketClient):
    """"""

    def __init__(self, gateway: BinancesGateway):
        """"""
        super().__init__()

        self.gateway: BinancesGateway = gateway
        self.gateway_name: str = gateway.gateway_name
        self.accountid = ""

    def connect(self, url: str, proxy_host: str, proxy_port: int) -> None:
        """"""
        self.init(url, proxy_host, proxy_port)
        self.start()

    def on_connected(self) -> None:
        """"""
        self.gateway.write_log("交易Websocket API连接成功")
        self.gateway.status.update({'tdws_con': True, 'tdws_con_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        if self.gateway.status.get('td_con', False):
            self.gateway.status.update({'con': True})

    def on_packet(self, packet: dict) -> None:  # type: (dict)->None
        """"""
        if packet["e"] == "ACCOUNT_UPDATE":
            self.on_account(packet)
        elif packet["e"] == "ORDER_TRADE_UPDATE":
            self.on_order(packet)

    def on_account(self, packet: dict) -> None:
        """
        websocket返回得Balance/Position信息更新
        """
        if not self.accountid:
            self.accountid = f"{self.gateway_name}_USDT"
        for acc_data in packet["a"]["B"]:
            account = AccountData(
                accountid=acc_data["a"],
                balance=float(acc_data["wb"]),
                frozen=float(acc_data["wb"]) - float(acc_data["cw"]),
                gateway_name=self.gateway_name
            )

            if account.balance:
                self.gateway.on_account(account)

        for pos_data in packet["a"]["P"]:
            position = PositionData(
                symbol=pos_data["s"],
                exchange=Exchange.BINANCE,
                direction=Direction.NET,
                volume=int(float(pos_data["pa"])),
                price=float(pos_data["ep"]),
                pnl=float(pos_data["cr"]),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_position(position)

    def on_order(self, packet: dict) -> None:
        """"""
        ord_data = packet["o"]
        key = (ord_data["o"], ord_data["f"])
        order_type = ORDERTYPE_BINANCES2VT.get(key, None)
        if not order_type:
            return

        dt = generate_datetime(packet["E"])

        order = OrderData(
            symbol=ord_data["s"],
            exchange=Exchange.BINANCE,
            orderid=str(ord_data["c"]),
            type=order_type,
            direction=DIRECTION_BINANCES2VT[ord_data["S"]],
            price=float(ord_data["p"]),
            volume=float(ord_data["q"]),
            traded=float(ord_data["z"]),
            status=STATUS_BINANCES2VT[ord_data["X"]],
            datetime=dt,
            gateway_name=self.gateway_name,
            offset=OFFSET_BINANCES2VT[ord_data['R']],
            time=dt.time()
        )

        if "n" in ord_data.keys():
            order.fee = float(ord_data['n'])
            order.netpnl = float(ord_data['rp'])

        self.gateway.on_order(order)

        # Push trade event
        trade_volume = float(ord_data["l"])
        if not trade_volume:
            return

        trade = TradeData(
            symbol=order.symbol,
            exchange=order.exchange,
            orderid=order.orderid,
            tradeid=ord_data["t"],
            direction=order.direction,
            price=float(ord_data["L"]),
            volume=trade_volume,
            datetime=generate_datetime(ord_data["T"]),
            gateway_name=self.gateway_name,
            offset=order.offset
        )
        self.gateway.on_trade(trade)


class BinancesDataWebsocketApi(WebsocketClient):
    """"""

    def __init__(self, gateway: BinancesGateway):
        """"""
        super().__init__()

        self.gateway: BinancesGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.ticks: Dict[str, TickData] = {}
        self.bars: Dict[str, BarData] = {}
        self.usdt_base = False

    def connect(
            self,
            usdt_base: bool,
            proxy_host: str,
            proxy_port: int,
            server: str
    ) -> None:
        """"""
        self.usdt_base = usdt_base
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.server = server

    def on_connected(self) -> None:
        """"""
        self.gateway.write_log("行情Websocket API连接刷新")
        self.gateway.status.update({'md_con': True, 'md_con_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        if self.gateway.status.get('td_con', False):
            self.gateway.status.update({'con': True})

    def subscribe(self, req: SubscribeRequest) -> None:
        """"""
        if req.symbol not in symbol_name_map:
            self.gateway.write_log(f"找不到该合约代码{req.symbol}")
            return

        # Create tick buf data
        tick = TickData(
            symbol=req.symbol,
            name=symbol_name_map.get(req.symbol, ""),
            exchange=Exchange.BINANCE,
            datetime=datetime.now(CHINA_TZ),
            gateway_name=self.gateway_name,
        )
        self.ticks[req.symbol.lower()] = tick

        bar = BarData(
            symbol=req.symbol,
            exchange=Exchange.BINANCE,
            datetime=datetime.now(CHINA_TZ),
            gateway_name=self.gateway_name,
            interval=Interval.MINUTE
        )
        self.bars[req.symbol.lower()] = bar

        # Close previous connection
        if self._active:
            self.stop()
            self.join()

        # Create new connection
        channels = []
        for ws_symbol in self.ticks.keys():
            channels.append(ws_symbol + "@ticker")
            channels.append(ws_symbol + "@kline_1m")
            channels.append(ws_symbol + "@depth20")

        if self.server == "REAL":
            url = F_WEBSOCKET_DATA_HOST + "/".join(channels)
            if not self.usdt_base:
                url = D_WEBSOCKET_DATA_HOST + "/".join(channels)
        else:
            url = F_TESTNET_WEBSOCKET_DATA_HOST + "/".join(channels)
            if not self.usdt_base:
                url = D_TESTNET_WEBSOCKET_DATA_HOST + "/".join(channels)

        self.init(url, self.proxy_host, self.proxy_port)
        self.start()

    def on_packet(self, packet: dict) -> None:
        """"""
        stream = packet["stream"]
        data = packet["data"]

        symbol, channel = stream.split("@")
        tick = self.ticks[symbol]

        if channel == "ticker":
            tick.volume = float(data['v'])
            tick.open_price = float(data['o'])
            tick.high_price = float(data['h'])
            tick.low_price = float(data['l'])
            tick.last_price = float(data['c'])
            tick.datetime = datetime.fromtimestamp(float(data['E']) / 1000)

            if tick.last_price:
                last_price_map[symbol.upper()] = tick.last_price
                self.gateway.on_tick(copy(tick))
        elif channel == "kline_1m":
            bar = self.bars[symbol]
            kline = data['k']
            bar.volume = float(kline['v'])
            bar.open_price = float(kline['o'])
            bar.close_price = float(kline['c'])
            bar.high_price = float(kline['h'])
            bar.low_price = float(kline['l'])
            bar.open_interest = float(kline['n'])
            bar.datetime = datetime.fromtimestamp(float(kline['t']) / 1000)

            if kline['x']:
                self.gateway.on_bar(copy(bar))
        else:
            bids = data["b"]
            for n in range(5):
                price, volume = bids[n]
                tick.__setattr__("bid_price_" + str(n + 1), float(price))
                tick.__setattr__("bid_volume_" + str(n + 1), float(volume))

            asks = data["a"]
            for n in range(5):
                price, volume = asks[n]
                tick.__setattr__("ask_price_" + str(n + 1), float(price))
                tick.__setattr__("ask_volume_" + str(n + 1), float(volume))

            tick.datetime = datetime.fromtimestamp(float(data['E']) / 1000)

            if tick.last_price:
                self.gateway.on_tick(copy(tick))


def generate_datetime(timestamp: float) -> datetime:
    """"""
    dt = datetime.fromtimestamp(timestamp / 1000)
    dt = CHINA_TZ.localize(dt)
    return dt
