"""
MT5Connector: Bridge between TradingAgents and MetaTrader 5.

Supports multiple connection methods:
1. Native MetaTrader5 Python library (Windows/Linux with MT5 terminal)
2. REST API endpoint (alternative approach)
3. Mock mode for development/testing

Usage:
    # Connect to demo account
    connector = MT5Connector(account_type="demo", broker="icmarkets")
    if connector.connect():
        info = connector.get_account_info()
        print(f"Account: {info.login}, Balance: {info.balance}")
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime
from abc import ABC, abstractmethod

from tradingagents.brokers.models import (
    AccountInfo, SymbolInfo, Position, OrderStatus,
    MT5Order, OrderAction, OrderType
)
from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)


class MT5ConnectorBase(ABC):
    """Abstract base for MT5 connection implementations."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to MT5."""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """Close connection to MT5."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""
        pass

    @abstractmethod
    def get_account_info(self) -> Optional[AccountInfo]:
        """Get account information."""
        pass

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information."""
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get existing position for symbol."""
        pass

    @abstractmethod
    def place_order(self, order: MT5Order) -> Dict:
        """Place order and return result."""
        pass

    @abstractmethod
    def close_position(self, ticket: int, volume: float) -> Dict:
        """Close or reduce position."""
        pass

    @abstractmethod
    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Modify stop loss and take profit."""
        pass


class NativeMT5Connector(MT5ConnectorBase):
    """
    Uses native MetaTrader5 Python library.

    Requirements:
    - Windows or Linux with MetaTrader 5 terminal running
    - MetaTrader5 Python package: pip install MetaTrader5
    """

    def __init__(self, login: int, password: str, server: str):
        """
        Initialize native MT5 connector.

        Args:
            login: MT5 account login
            password: MT5 account password
            server: MT5 server (e.g., "ICMarkets-Demo", "ICMarkets-Live")
        """
        self.login = login
        self.password = password
        self.server = server
        self._mt5 = None
        self._connected = False

        # Try to import MT5
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            logger.error(
                "MetaTrader5 library not installed. "
                "Install with: pip install MetaTrader5 "
                "(Windows/Linux with MT5 terminal only)"
            )
            self._mt5 = None

    def connect(self) -> bool:
        """Connect to MT5 terminal."""
        if not self._mt5:
            logger.error("MT5 library not available")
            return False

        try:
            if not self._mt5.initialize(
                login=self.login,
                password=self.password,
                server=self.server
            ):
                logger.error(f"Failed to initialize MT5: {self._mt5.last_error()}")
                return False

            self._connected = True
            info = self._mt5.account_info()
            logger.info(f"Connected to MT5: {info.login} on {info.server}")
            return True

        except Exception as e:
            logger.error(f"Error connecting to MT5: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from MT5."""
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False
            return True
        return False

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self._mt5 is not None

    def get_account_info(self) -> Optional[AccountInfo]:
        """Get account information from MT5."""
        if not self.is_connected():
            return None

        try:
            acc = self._mt5.account_info()
            return AccountInfo(
                login=acc.login,
                server=acc.server,
                account_type="REAL" if acc.trade_allowed else "DEMO",
                currency=acc.currency,
                balance=float(acc.balance),
                equity=float(acc.equity),
                free_margin=float(acc.margin_free),
                margin_level=float(acc.margin_level),
            )
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information from MT5."""
        if not self.is_connected():
            return None

        try:
            sym = self._mt5.symbol_info(symbol)
            if sym is None:
                logger.warning(f"Symbol {symbol} not found")
                return None

            tick = self._mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.warning(f"Cannot get tick for {symbol}")
                return None

            # MT5 reports tick value per `trade_tick_size`; rescale to per-`point`
            # so it matches the unit used by risk-based sizing (risk in points).
            point = float(sym.point)
            tick_value = float(getattr(sym, "trade_tick_value", 0.0) or 0.0)
            tick_size = float(getattr(sym, "trade_tick_size", 0.0) or 0.0)
            pip_value_per_lot = (
                tick_value * (point / tick_size)
                if tick_value > 0 and tick_size > 0 and point > 0
                else None
            )

            return SymbolInfo(
                symbol=symbol,
                bid=float(tick.bid),
                ask=float(tick.ask),
                spread=(float(tick.ask) - float(tick.bid)) / sym.point if sym.point else 0,
                digits=sym.digits,
                point=point,
                min_volume=float(sym.volume_min),
                max_volume=float(sym.volume_max),
                volume_step=float(sym.volume_step),
                pip_value_per_lot=pip_value_per_lot,
                swap_long=float(sym.swap_long) if sym.swap_long else None,
                swap_short=float(sym.swap_short) if sym.swap_short else None,
            )
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get existing position for symbol."""
        if not self.is_connected():
            return None

        try:
            positions = self._mt5.positions_get(symbol=symbol)
            if not positions:
                return None

            pos = positions[0]  # Get first position
            return Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                type=OrderAction.BUY if pos.type == 0 else OrderAction.SELL,
                volume=float(pos.volume),
                entry_price=float(pos.price_open),
                current_price=float(pos.price_current),
                profit=float(pos.profit),
                profit_percent=(float(pos.profit) / abs(pos.volume * pos.price_open)) * 100
                    if pos.volume and pos.price_open else 0,
                stop_loss=float(pos.sl) if pos.sl else None,
                take_profit=float(pos.tp) if pos.tp else None,
                open_time=datetime.fromtimestamp(pos.time),
                open_comment=pos.comment,
            )
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {e}")
            return None

    def place_order(self, order: MT5Order) -> Dict:
        """Place order on MT5."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected to MT5"}

        try:
            symbol_info = self.get_symbol_info(order.symbol)
            if not symbol_info:
                return {"status": "error", "message": f"Symbol {order.symbol} not found"}

            # Map order type
            mt5_order_type = {
                OrderType.MARKET: self._mt5.ORDER_TYPE_BUY if order.action == OrderAction.BUY else self._mt5.ORDER_TYPE_SELL,
                OrderType.LIMIT: self._mt5.ORDER_TYPE_BUY_LIMIT if order.action == OrderAction.BUY else self._mt5.ORDER_TYPE_SELL_LIMIT,
            }.get(order.order_type, self._mt5.ORDER_TYPE_BUY if order.action == OrderAction.BUY else self._mt5.ORDER_TYPE_SELL)

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": order.symbol,
                "volume": order.volume,
                "type": mt5_order_type,
                "price": order.entry_price or symbol_info.ask if order.action == OrderAction.BUY else symbol_info.bid,
                "sl": order.stop_loss,
                "tp": order.take_profit,
                "comment": order.comment or f"TradingAgents:{order.decision_id}",
            }

            result = self._mt5.order_send(request)
            if result.retcode == self._mt5.TRADE_RETCODE_DONE:
                return {
                    "status": "executed",
                    "ticket": result.order,
                    "volume": result.volume,
                    "price": result.price,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Order failed: {result.comment}",
                    "retcode": result.retcode,
                }
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {"status": "error", "message": str(e)}

    def close_position(self, ticket: int, volume: float) -> Dict:
        """Close or reduce position."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected to MT5"}

        try:
            position = None
            for pos in self._mt5.positions_get():
                if pos.ticket == ticket:
                    position = pos
                    break

            if not position:
                return {"status": "error", "message": f"Position {ticket} not found"}

            order_type = self._mt5.ORDER_TYPE_SELL if position.type == 0 else self._mt5.ORDER_TYPE_BUY
            current_price = self.get_symbol_info(position.symbol).bid if position.type == 0 else self.get_symbol_info(position.symbol).ask

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "price": current_price,
                "comment": f"Close:{ticket}",
            }

            result = self._mt5.order_send(request)
            if result.retcode == self._mt5.TRADE_RETCODE_DONE:
                return {"status": "closed", "deal": result.deal}
            else:
                return {"status": "error", "message": result.comment}
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {"status": "error", "message": str(e)}

    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Modify stop loss and take profit."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected to MT5"}

        try:
            request = {
                "action": self._mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": sl,
                "tp": tp,
            }

            result = self._mt5.order_send(request)
            if result.retcode == self._mt5.TRADE_RETCODE_DONE:
                return {"status": "modified"}
            else:
                return {"status": "error", "message": result.comment}
        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            return {"status": "error", "message": str(e)}


class MockMT5Connector(MT5ConnectorBase):
    """
    Mock connector for development and testing.

    Simulates MT5 responses without actual connection.
    """

    def __init__(self, account_type="demo"):
        self.account_type = account_type
        self._connected = False
        self._positions: Dict[int, Position] = {}
        self._next_ticket = 1000

    def connect(self) -> bool:
        """Mock connect."""
        self._connected = True
        logger.info(f"Mock MT5 connected ({self.account_type} mode)")
        return True

    def disconnect(self) -> bool:
        """Mock disconnect."""
        self._connected = False
        return True

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    def get_account_info(self) -> Optional[AccountInfo]:
        """Return mock account info."""
        if not self.is_connected():
            return None

        return AccountInfo(
            login=123456,
            server="IC Markets - Demo" if self.account_type == "demo" else "IC Markets - Live",
            account_type="DEMO" if self.account_type == "demo" else "REAL",
            currency="USD",
            balance=10000.0,
            equity=10000.0,
            free_margin=9500.0,
            margin_level=110.0,
        )

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Return mock symbol info."""
        if not self.is_connected():
            return None

        # Mock data for common symbols. pip_value = account-USD value of one
        # `point` move per 1.0 lot (FX majors ~10, XAUUSD ~1, JPY pairs ~6.7).
        mock_data = {
            "EURUSD": {"bid": 1.0950, "ask": 1.0952, "point": 0.0001, "pip_value": 10.0},
            "GBPUSD": {"bid": 1.2650, "ask": 1.2652, "point": 0.0001, "pip_value": 10.0},
            "USDJPY": {"bid": 150.00, "ask": 150.02, "point": 0.01, "pip_value": 6.7},
            "XAUUSD": {"bid": 2000.00, "ask": 2000.30, "point": 0.01, "pip_value": 1.0},
            "AAPL": {"bid": 150.25, "ask": 150.27, "point": 0.01, "pip_value": 1.0},
            "NVDA": {"bid": 875.50, "ask": 875.75, "point": 0.01, "pip_value": 1.0},
        }

        if symbol not in mock_data:
            mock_data[symbol] = {"bid": 100.0, "ask": 100.02, "point": 0.01, "pip_value": 1.0}

        data = mock_data[symbol]
        return SymbolInfo(
            symbol=symbol,
            bid=data["bid"],
            ask=data["ask"],
            spread=(data["ask"] - data["bid"]) / data["point"],
            digits=4 if symbol.endswith("USD") or symbol.endswith("EUR") else 2,
            point=data["point"],
            min_volume=0.01,
            max_volume=1000.0,
            volume_step=0.01,
            pip_value_per_lot=data["pip_value"],
        )

    def get_position(self, symbol: str) -> Optional[Position]:
        """Return mock position if exists."""
        if not self.is_connected():
            return None

        for pos in self._positions.values():
            if pos.symbol == symbol:
                return pos
        return None

    def place_order(self, order: MT5Order) -> Dict:
        """Mock place order."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        ticket = self._next_ticket
        self._next_ticket += 1

        logger.info(f"Mock order placed: {order.action} {order.volume} {order.symbol} @ ticket {ticket}")
        return {
            "status": "executed",
            "ticket": ticket,
            "volume": order.volume,
            "price": order.entry_price or 100.0,
        }

    def close_position(self, ticket: int, volume: float) -> Dict:
        """Mock close position."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        if ticket in self._positions:
            del self._positions[ticket]
            logger.info(f"Mock position closed: ticket {ticket}")
            return {"status": "closed"}
        return {"status": "error", "message": f"Position {ticket} not found"}

    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Mock modify order."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        logger.info(f"Mock order modified: ticket {ticket}, SL={sl}, TP={tp}")
        return {"status": "modified"}


class MT5Connector:
    """
    Main MT5 connector with automatic backend selection.

    Tries to use native MetaTrader5 library if available,
    falls back to mock connector for development/testing.
    """

    def __init__(self, account_type=None, login: int = None,
                 password: str = None, server: str = None,
                 use_mock=False):
        """
        Initialize MT5 connector.

        Args:
            account_type: "demo" or "live" (uses config if not specified)
            login: MT5 login (optional if using mock)
            password: MT5 password (optional if using mock)
            server: MT5 server (optional if using mock)
            use_mock: Force use of mock connector
        """
        # Use provided account_type or read from config
        if account_type is None:
            config = get_config()
            trading_mode = config.get("trading_mode", "paper")
            # Map paper/live to demo/live convention
            account_type = "demo" if trading_mode == "paper" else "live"

        # Normalize account_type for backward compatibility
        if account_type.lower() in ["paper", "demo"]:
            self.account_type = "demo"
            logger.info("Trading mode: PAPER (demo account)")
        elif account_type.lower() in ["live", "real"]:
            self.account_type = "live"
            logger.warning("⚠️  Trading mode: LIVE (real money)")
        else:
            raise ValueError(f"Invalid account_type: {account_type}. Use 'demo', 'paper', 'live', or 'real'.")

        if use_mock:
            self._connector = MockMT5Connector(self.account_type)
            logger.info("Using mock MT5 connector (development mode)")
        else:
            # Try native connector first
            if login and password and server:
                self._connector = NativeMT5Connector(login, password, server)
                logger.info("Using native MT5 connector")
            else:
                # Fall back to mock
                self._connector = MockMT5Connector(self.account_type)
                logger.warning(
                    "Credentials not provided, using mock connector. "
                    "To use native MT5, provide login, password, and server."
                )

    def connect(self) -> bool:
        """Connect to MT5."""
        return self._connector.connect()

    def disconnect(self) -> bool:
        """Disconnect from MT5."""
        return self._connector.disconnect()

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connector.is_connected()

    def get_account_info(self) -> Optional[AccountInfo]:
        """Get account information."""
        return self._connector.get_account_info()

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information."""
        return self._connector.get_symbol_info(symbol)

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        return self._connector.get_position(symbol)

    def place_order(self, order: MT5Order) -> Dict:
        """Place order."""
        return self._connector.place_order(order)

    def close_position(self, ticket: int, volume: float) -> Dict:
        """Close position."""
        return self._connector.close_position(ticket, volume)

    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Modify order."""
        return self._connector.modify_order(ticket, sl, tp)
