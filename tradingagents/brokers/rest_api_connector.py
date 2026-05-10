"""
REST API connector for MT5.

Alternative to native MetaTrader5 library using REST API endpoint.
Useful for macOS and remote MT5 servers.

This is a template - requires a server running the MT5 REST API service.
"""

import logging
from typing import Optional, Dict
from requests import Session
from requests.exceptions import RequestException

from tradingagents.brokers.mt5_connector import MT5ConnectorBase
from tradingagents.brokers.models import (
    AccountInfo, SymbolInfo, Position, MT5Order, OrderAction
)

logger = logging.getLogger(__name__)


class RESTMT5Connector(MT5ConnectorBase):
    """
    MT5 connector via REST API.

    Connects to a remote MT5 server via HTTP REST API.
    Useful for:
    - macOS/unsupported platforms
    - Remote MT5 servers
    - Cloud deployment
    """

    def __init__(self, api_url: str, api_key: str = None, timeout: int = 30):
        """
        Initialize REST API connector.

        Args:
            api_url: Base URL of MT5 REST API (e.g., http://localhost:8080)
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._connected = False
        self.session = Session()

        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

        logger.info(f"REST MT5 Connector initialized: {api_url}")

    def connect(self) -> bool:
        """Connect to remote MT5 API."""
        try:
            response = self.session.get(
                f"{self.api_url}/health",
                timeout=self.timeout
            )

            if response.status_code == 200:
                self._connected = True
                logger.info("Connected to MT5 REST API")
                return True
            else:
                logger.error(f"Health check failed: {response.status_code}")
                return False

        except RequestException as e:
            logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self) -> bool:
        """Close connection."""
        self._connected = False
        self.session.close()
        return True

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    def get_account_info(self) -> Optional[AccountInfo]:
        """Get account info via REST."""
        if not self.is_connected():
            return None

        try:
            response = self.session.get(
                f"{self.api_url}/account",
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                return AccountInfo(
                    login=data.get("login"),
                    server=data.get("server"),
                    account_type=data.get("account_type"),
                    currency=data.get("currency"),
                    balance=float(data.get("balance", 0)),
                    equity=float(data.get("equity", 0)),
                    free_margin=float(data.get("free_margin", 0)),
                    margin_level=float(data.get("margin_level", 0)),
                )

        except Exception as e:
            logger.error(f"Error getting account info: {e}")

        return None

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol info via REST."""
        if not self.is_connected():
            return None

        try:
            response = self.session.get(
                f"{self.api_url}/symbols/{symbol}",
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                return SymbolInfo(
                    symbol=symbol,
                    bid=float(data.get("bid", 0)),
                    ask=float(data.get("ask", 0)),
                    spread=float(data.get("spread", 0)),
                    digits=int(data.get("digits", 4)),
                    point=float(data.get("point", 0.0001)),
                    min_volume=float(data.get("min_volume", 0.01)),
                    max_volume=float(data.get("max_volume", 1000)),
                    volume_step=float(data.get("volume_step", 0.01)),
                )

        except Exception as e:
            logger.error(f"Error getting symbol {symbol}: {e}")

        return None

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position via REST."""
        if not self.is_connected():
            return None

        try:
            response = self.session.get(
                f"{self.api_url}/positions/{symbol}",
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()

                from datetime import datetime
                return Position(
                    ticket=data.get("ticket"),
                    symbol=symbol,
                    type=OrderAction.BUY if data.get("type") == "BUY" else OrderAction.SELL,
                    volume=float(data.get("volume", 0)),
                    entry_price=float(data.get("entry_price", 0)),
                    current_price=float(data.get("current_price", 0)),
                    profit=float(data.get("profit", 0)),
                    profit_percent=float(data.get("profit_percent", 0)),
                    stop_loss=float(data.get("stop_loss")) if data.get("stop_loss") else None,
                    take_profit=float(data.get("take_profit")) if data.get("take_profit") else None,
                    open_time=datetime.fromisoformat(data.get("open_time", "2026-01-01T00:00:00")),
                )

        except Exception as e:
            logger.error(f"Error getting position {symbol}: {e}")

        return None

    def place_order(self, order: MT5Order) -> Dict:
        """Place order via REST."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        try:
            payload = {
                "symbol": order.symbol,
                "action": order.action.value,
                "volume": order.volume,
                "entry_price": order.entry_price,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "comment": order.comment or order.decision_id,
            }

            response = self.session.post(
                f"{self.api_url}/orders",
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 201:
                data = response.json()
                return {
                    "status": "executed",
                    "ticket": data.get("ticket"),
                    "volume": data.get("volume"),
                    "price": data.get("price"),
                }
            else:
                return {
                    "status": "error",
                    "message": response.json().get("error", "Unknown error")
                }

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {"status": "error", "message": str(e)}

    def close_position(self, ticket: int, volume: float) -> Dict:
        """Close position via REST."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        try:
            response = self.session.post(
                f"{self.api_url}/positions/{ticket}/close",
                json={"volume": volume},
                timeout=self.timeout
            )

            if response.status_code == 200:
                return {"status": "closed"}
            else:
                return {
                    "status": "error",
                    "message": response.json().get("error", "Unknown error")
                }

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {"status": "error", "message": str(e)}

    def modify_order(self, ticket: int, sl: float, tp: float) -> Dict:
        """Modify order via REST."""
        if not self.is_connected():
            return {"status": "error", "message": "Not connected"}

        try:
            response = self.session.put(
                f"{self.api_url}/positions/{ticket}",
                json={"stop_loss": sl, "take_profit": tp},
                timeout=self.timeout
            )

            if response.status_code == 200:
                return {"status": "modified"}
            else:
                return {
                    "status": "error",
                    "message": response.json().get("error", "Unknown error")
                }

        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            return {"status": "error", "message": str(e)}


class MT5WebSocketConnector:
    """
    WebSocket connector for real-time MT5 updates.

    Provides live price feeds and position updates via WebSocket.
    """

    def __init__(self, ws_url: str):
        """
        Initialize WebSocket connector.

        Args:
            ws_url: WebSocket URL (e.g., ws://localhost:8080/ws)
        """
        self.ws_url = ws_url
        self._ws = None

    def connect(self) -> bool:
        """Connect to WebSocket."""
        try:
            import websocket
            self._ws = websocket.WebSocketApp(
                self.ws_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            logger.info(f"WebSocket connected: {self.ws_url}")
            return True
        except ImportError:
            logger.error("websocket-client library not installed. Install with: pip install websocket-client")
            return False
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False

    def subscribe_to_symbol(self, symbol: str) -> None:
        """Subscribe to real-time updates for a symbol."""
        if self._ws:
            self._ws.send(f'{{"action": "subscribe", "symbol": "{symbol}"}}')

    def disconnect(self) -> None:
        """Close WebSocket."""
        if self._ws:
            self._ws.close()

    def _on_message(self, ws, message):
        """Handle incoming WebSocket message."""
        logger.debug(f"WebSocket message: {message}")

    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        logger.info("WebSocket closed")
