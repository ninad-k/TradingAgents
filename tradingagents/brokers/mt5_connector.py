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
import os
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from tradingagents.brokers.models import (
    AccountInfo, SymbolInfo, Position, OrderStatus,
    MT5Order, OrderAction, OrderType, TradeRecord
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
    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        pass

    @abstractmethod
    def get_trade_history(self, days: int = 7, limit: int = 50) -> List[TradeRecord]:
        """Get recent broker trade/deal history."""
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

    @abstractmethod
    def list_symbols(self, refresh: bool = False) -> List[Dict]:
        """Return all symbols the broker exposes.

        Each entry is a dict with: ``name``, ``description``, ``path``,
        ``category`` (top-level folder, e.g. ``Forex``), ``currency_base``,
        ``currency_profit``, ``digits``, ``visible``.

        Results may be cached after the first call; pass ``refresh=True`` to
        force a fresh fetch.
        """
        pass


class NativeMT5Connector(MT5ConnectorBase):
    """
    Uses native MetaTrader5 Python library.

    Requirements:
    - Windows or Linux with MetaTrader 5 terminal running
    - MetaTrader5 Python package: pip install MetaTrader5
    """

    def __init__(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None):
        """
        Initialize native MT5 connector.

        Args:
            login: MT5 account login. Optional when attaching to an already-open terminal.
            password: MT5 account password. Optional when attaching to an already-open terminal.
            server: MT5 server. Optional when attaching to an already-open terminal.
        """
        self.login = login
        self.password = password
        self.server = server
        self._mt5 = None
        self._connected = False
        self._symbols_cache: Optional[List[Dict]] = None

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
            init_kwargs = {}
            if self.login and self.password and self.server:
                init_kwargs = {
                    "login": self.login,
                    "password": self.password,
                    "server": self.server,
                }

            if not self._mt5.initialize(**init_kwargs):
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

    def get_positions(self) -> List[Position]:
        """Get all open MT5 positions."""
        if not self.is_connected():
            return []

        try:
            positions = self._mt5.positions_get()
            if not positions:
                return []
            return [self._position_from_mt5(pos) for pos in positions]
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []

    def list_symbols(self, refresh: bool = False) -> List[Dict]:
        """Snapshot all broker symbols. Cached after first call.

        Cache is invalidated when ``refresh=True``. Reads via ``mt5.symbols_get``
        which returns SymbolInfo tuples; we coerce to a JSON-friendly dict so
        the API can serve it directly.
        """
        if self._symbols_cache is not None and not refresh:
            return self._symbols_cache
        if not self.is_connected() and not self.connect():
            return []
        try:
            raw = self._mt5.symbols_get() or []
        except Exception as e:
            logger.error(f"Error listing broker symbols: {e}")
            return []
        entries: List[Dict] = []
        for sym in raw:
            path = getattr(sym, "path", "") or ""
            # First segment of path is the broker category, e.g. "Forex\\Majors\\EURUSD" → "Forex"
            category = path.split("\\")[0] if path else ""
            entries.append({
                "name": getattr(sym, "name", ""),
                "description": getattr(sym, "description", "") or "",
                "path": path,
                "category": category,
                "currency_base": getattr(sym, "currency_base", "") or "",
                "currency_profit": getattr(sym, "currency_profit", "") or "",
                "digits": int(getattr(sym, "digits", 0) or 0),
                "visible": bool(getattr(sym, "visible", False)),
            })
        # Sort by category then name so the picker is browsable.
        entries.sort(key=lambda e: (e["category"], e["name"]))
        self._symbols_cache = entries
        return entries

    def _position_from_mt5(self, pos) -> Position:
        # MT5 returns Unix epoch seconds; use UTC to match `datetime.utcnow()`
        # used elsewhere in the dashboard. profit_percent is set to 0.0
        # because computing it correctly needs margin-at-open, which the
        # MT5 position struct doesn't expose; the dashboard already shows
        # the absolute profit field.
        return Position(
            ticket=pos.ticket,
            symbol=pos.symbol,
            type=OrderAction.BUY if pos.type == 0 else OrderAction.SELL,
            volume=float(pos.volume),
            entry_price=float(pos.price_open),
            current_price=float(pos.price_current),
            profit=float(pos.profit),
            profit_percent=0.0,
            stop_loss=float(pos.sl) if pos.sl else None,
            take_profit=float(pos.tp) if pos.tp else None,
            open_time=datetime.utcfromtimestamp(pos.time),
            open_comment=getattr(pos, "comment", None),
        )

    def get_trade_history(self, days: int = 7, limit: int = 50) -> List[TradeRecord]:
        """Pair MT5 deals by position_id and return round-trip TradeRecords."""
        if not self.is_connected():
            return []

        try:
            now = datetime.utcnow()
            deals = self._mt5.history_deals_get(now - timedelta(days=days), now)
            if not deals:
                return []

            deal_entry_in = getattr(self._mt5, "DEAL_ENTRY_IN", 0)
            deal_entry_out = getattr(self._mt5, "DEAL_ENTRY_OUT", 1)

            # Walk deals oldest-first so the IN deal always lands before its OUT.
            grouped: Dict[int, TradeRecord] = {}
            for deal in sorted(deals, key=lambda d: d.time):
                # Skip balance/credit/commission deals that aren't trades.
                if getattr(deal, "symbol", "") == "":
                    continue
                position_id = int(getattr(deal, "position_id", deal.ticket) or deal.ticket)
                deal_type = getattr(deal, "type", None)
                action = OrderAction.BUY if deal_type == self._mt5.DEAL_TYPE_BUY else OrderAction.SELL
                entry_flag = getattr(deal, "entry", None)
                deal_time = datetime.utcfromtimestamp(deal.time)
                price = float(deal.price)
                profit = float(getattr(deal, "profit", 0.0) or 0.0)
                comment = getattr(deal, "comment", None)

                existing = grouped.get(position_id)
                if existing is None:
                    # First deal seen for this position — treat as entry.
                    grouped[position_id] = TradeRecord(
                        symbol=deal.symbol,
                        action=action,
                        volume=float(deal.volume),
                        entry_price=price,
                        entry_time=deal_time,
                        status="closed" if entry_flag == deal_entry_out else "open",
                        ticket=int(deal.ticket),
                        position_id=position_id,
                        profit=profit if entry_flag == deal_entry_out else None,
                        comment=comment,
                    )
                    # If the only deal we have is an OUT (rare — partial history
                    # window), exit_* mirrors entry_* so the dashboard at least
                    # shows the exit price.
                    if entry_flag == deal_entry_out:
                        grouped[position_id].exit_price = price
                        grouped[position_id].exit_time = deal_time
                else:
                    # Subsequent deal — treat as the closing leg.
                    existing.exit_price = price
                    existing.exit_time = deal_time
                    existing.status = "closed"
                    existing.profit = (existing.profit or 0.0) + profit

            # Newest entries first; apply caller's limit.
            records = sorted(grouped.values(), key=lambda r: r.entry_time, reverse=True)
            return records[:limit]
        except Exception as e:
            logger.error(f"Error getting trade history: {e}")
            return []

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

            price = order.entry_price
            if price is None:
                price = symbol_info.ask if order.action == OrderAction.BUY else symbol_info.bid

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": order.symbol,
                "volume": order.volume,
                "type": mt5_order_type,
                "price": price,
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
        # Keyed by ticket (used as position_id in the mock) so close_position
        # can update the same record rather than appending a sibling.
        self._trade_history: Dict[int, TradeRecord] = {}
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

    def get_positions(self) -> List[Position]:
        """Return all mock positions."""
        if not self.is_connected():
            return []
        return list(self._positions.values())

    def get_trade_history(self, days: int = 7, limit: int = 50) -> List[TradeRecord]:
        """Return mock trade history, newest entry first."""
        if not self.is_connected():
            return []
        records = sorted(self._trade_history.values(), key=lambda r: r.entry_time, reverse=True)
        return records[:limit]

    def place_order(self, order: MT5Order) -> Dict:
        """Mock place order."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        ticket = self._next_ticket
        self._next_ticket += 1
        symbol_info = self.get_symbol_info(order.symbol)
        price = order.entry_price
        if price is None and symbol_info:
            price = symbol_info.ask if order.action == OrderAction.BUY else symbol_info.bid
        if price is None:
            price = 100.0

        position = Position(
            ticket=ticket,
            symbol=order.symbol,
            type=order.action,
            volume=order.volume,
            entry_price=price,
            current_price=price,
            profit=0.0,
            profit_percent=0.0,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            open_time=datetime.utcnow(),
            open_comment=order.comment,
            decision_id=order.decision_id,
        )
        self._positions[ticket] = position
        self._trade_history[ticket] = TradeRecord(
            symbol=order.symbol,
            action=order.action,
            volume=order.volume,
            entry_price=price,
            entry_time=position.open_time,
            status="open",
            ticket=ticket,
            position_id=ticket,
            profit=None,
            comment=order.comment,
        )

        logger.info(f"Mock order placed: {order.action} {order.volume} {order.symbol} @ ticket {ticket}")
        return {
            "status": "executed",
            "ticket": ticket,
            "volume": order.volume,
            "price": price,
        }

    def close_position(self, ticket: int, volume: float) -> Dict:
        """Mock close position."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        if ticket in self._positions:
            position = self._positions.pop(ticket)
            now = datetime.utcnow()
            existing = self._trade_history.get(ticket)
            if existing is not None:
                existing.exit_price = position.current_price
                existing.exit_time = now
                existing.status = "closed"
                existing.profit = position.profit
            else:
                # No open-side record (shouldn't normally happen); synthesize one.
                self._trade_history[ticket] = TradeRecord(
                    symbol=position.symbol,
                    action=position.type,
                    volume=volume,
                    entry_price=position.entry_price,
                    entry_time=position.open_time,
                    exit_price=position.current_price,
                    exit_time=now,
                    status="closed",
                    ticket=ticket,
                    position_id=ticket,
                    profit=position.profit,
                    comment=position.open_comment,
                )
            logger.info(f"Mock position closed: ticket {ticket}")
            return {"status": "closed"}
        return {"status": "error", "message": f"Position {ticket} not found"}

    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Mock modify order."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        logger.info(f"Mock order modified: ticket {ticket}, SL={sl}, TP={tp}")
        return {"status": "modified"}

    def list_symbols(self, refresh: bool = False) -> List[Dict]:
        """Return a small canned universe so tests and demo runs have data."""
        catalog = [
            ("EURUSD", "Euro vs US Dollar",            "Forex\\Majors\\EURUSD",     "Forex",      "EUR", "USD", 5),
            ("GBPUSD", "British Pound vs US Dollar",   "Forex\\Majors\\GBPUSD",     "Forex",      "GBP", "USD", 5),
            ("USDJPY", "US Dollar vs Japanese Yen",    "Forex\\Majors\\USDJPY",     "Forex",      "USD", "JPY", 3),
            ("AUDUSD", "Australian Dollar vs USD",     "Forex\\Majors\\AUDUSD",     "Forex",      "AUD", "USD", 5),
            ("USDCAD", "US Dollar vs Canadian Dollar", "Forex\\Majors\\USDCAD",     "Forex",      "USD", "CAD", 5),
            ("XAUUSD", "Gold vs US Dollar",            "Metals\\XAUUSD",            "Metals",     "XAU", "USD", 2),
            ("XAGUSD", "Silver vs US Dollar",          "Metals\\XAGUSD",            "Metals",     "XAG", "USD", 3),
            ("BTCUSD", "Bitcoin vs US Dollar",         "Crypto\\BTCUSD",            "Crypto",     "BTC", "USD", 2),
            ("ETHUSD", "Ethereum vs US Dollar",        "Crypto\\ETHUSD",            "Crypto",     "ETH", "USD", 2),
            ("NAS100", "Nasdaq 100 Index",             "Indices\\NAS100",           "Indices",    "USD", "USD", 2),
            ("US500",  "S&P 500 Index",                "Indices\\US500",            "Indices",    "USD", "USD", 2),
            ("USOIL",  "WTI Crude Oil",                "Commodities\\USOIL",        "Commodities","USD", "USD", 2),
        ]
        return [
            {
                "name": n, "description": d, "path": p, "category": c,
                "currency_base": cb, "currency_profit": cp, "digits": dg,
                "visible": True,
            }
            for n, d, p, c, cb, cp, dg in catalog
        ]


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
        login = login if login is not None else self._env_int("MT5_LOGIN")
        password = password if password is not None else os.getenv("MT5_PASSWORD")
        server = server if server is not None else os.getenv("MT5_SERVER")
        env_use_mock = os.getenv("MT5_USE_MOCK")
        if env_use_mock is not None:
            use_mock = env_use_mock.strip().lower() in {"1", "true", "yes", "on"}

        # Use provided account_type or read from config
        if account_type is None:
            config = get_config()
            trading_mode = os.getenv("MT5_ACCOUNT_TYPE") or config.get("trading_mode", "paper")
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
            self._connector = NativeMT5Connector(login, password, server)
            if login and password and server:
                logger.info("Using native MT5 connector with configured credentials")
            else:
                logger.info("Using native MT5 connector with the currently open terminal session")

    @staticmethod
    def _env_int(name: str) -> Optional[int]:
        value = os.getenv(name)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            logger.warning("Invalid integer for %s: %s", name, value)
            return None

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

    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        return self._connector.get_positions()

    def get_trade_history(self, days: int = 7, limit: int = 50) -> List[TradeRecord]:
        """Get recent broker trade history."""
        return self._connector.get_trade_history(days=days, limit=limit)

    def place_order(self, order: MT5Order) -> Dict:
        """Place order."""
        return self._connector.place_order(order)

    def close_position(self, ticket: int, volume: float) -> Dict:
        """Close position."""
        return self._connector.close_position(ticket, volume)

    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Modify order."""
        return self._connector.modify_order(ticket, sl, tp)

    def list_symbols(self, refresh: bool = False) -> List[Dict]:
        """List all broker symbols (cached after first call)."""
        return self._connector.list_symbols(refresh=refresh)


_SHARED_CONNECTOR: Optional[MT5Connector] = None


def get_shared_mt5_connector(account_type: Optional[str] = None) -> MT5Connector:
    """Return the process-wide broker connector used by API and scheduler."""
    global _SHARED_CONNECTOR
    if _SHARED_CONNECTOR is None:
        _SHARED_CONNECTOR = MT5Connector(account_type=account_type)
    return _SHARED_CONNECTOR
