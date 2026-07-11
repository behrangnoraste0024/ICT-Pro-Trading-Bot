from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from models.binance_futures_testnet_adapter import BinanceFuturesTestnetAdapterConfig


class BinanceFuturesTestnetOperationBlocked(RuntimeError):
    pass


@dataclass
class BinancePublicResponse:
    status_code: int
    final_url: str
    payload: Any


class BinanceFuturesTestnetAdapter:
    ALLOWED_HOST = "demo-fapi.binance.com"
    BLOCKED_DECISION = "AUTHENTICATED_TESTNET_OPERATION_DISABLED"

    def __init__(self, config: BinanceFuturesTestnetAdapterConfig, http_get=None, env: dict[str, str] | None = None) -> None:
        self.config = config
        self.http_get = http_get or self._default_http_get
        self.env = {} if env is None else env
        self.validate_base_url(config.rest_base_url)

    def ping(self) -> dict[str, Any]:
        response = self._public_get("/fapi/v1/ping")
        return {"ok": True, "http_status": response.status_code, "final_host": urlparse(response.final_url).hostname, "payload": response.payload}

    def fetch_server_time(self) -> dict[str, Any]:
        response = self._public_get("/fapi/v1/time")
        if not isinstance(response.payload, dict) or not isinstance(response.payload.get("serverTime"), int):
            raise ValueError("serverTime payload is invalid")
        return {"server_time": response.payload["serverTime"], "http_status": response.status_code, "final_host": urlparse(response.final_url).hostname}

    def fetch_exchange_info(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        response = self._public_get("/fapi/v1/exchangeInfo")
        symbols = response.payload.get("symbols") if isinstance(response.payload, dict) else None
        if not isinstance(symbols, list):
            raise ValueError("exchangeInfo payload is invalid")
        row = next((item for item in symbols if isinstance(item, dict) and item.get("symbol") == symbol), None)
        if row is None:
            raise ValueError(f"{symbol} not found in exchangeInfo")
        return {
            "symbol": row.get("symbol"),
            "pair": row.get("pair"),
            "contractType": row.get("contractType"),
            "status": row.get("status"),
            "baseAsset": row.get("baseAsset"),
            "quoteAsset": row.get("quoteAsset"),
            "http_status": response.status_code,
            "final_host": urlparse(response.final_url).hostname,
        }

    def inspect_credential_presence(self) -> dict[str, Any]:
        key = self.env.get(self.config.api_key_env_var)
        secret = self.env.get(self.config.api_secret_env_var)
        return {
            "api_key_present": bool(key),
            "api_secret_present": bool(secret),
            "api_key_length": len(key or ""),
            "api_secret_length": len(secret or ""),
            "credentials_complete": bool(key and secret),
            "credential_source": self.config.credential_source,
            "environment_names_valid": self.config.api_key_env_var == "BINANCE_FUTURES_TESTNET_API_KEY" and self.config.api_secret_env_var == "BINANCE_FUTURES_TESTNET_API_SECRET",
        }

    def build_signed_request_preview(self, path: str, parameters: dict[str, Any]) -> dict[str, Any]:
        self._require_allowed_preview_path(path)
        timestamp = parameters.get("timestamp")
        recv_window = int(parameters.get("recvWindow", self.config.recv_window_ms))
        if timestamp is None or int(timestamp) <= 0:
            raise ValueError("timestamp must be positive")
        if recv_window <= 0 or recv_window > int(self.config.maximum_recv_window_ms):
            raise ValueError("recvWindow is invalid")
        creds = self.inspect_credential_presence()
        canonical = self._canonical_query({**parameters, "recvWindow": recv_window})
        secret = self.env.get(self.config.api_secret_env_var)
        signature = None
        if secret:
            signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "method": "GET",
            "testnet_host": self.ALLOWED_HOST,
            "path": path,
            "canonical_parameter_names": sorted(parameters.keys() | {"recvWindow"}),
            "canonical_query_length": len(canonical),
            "timestamp": int(timestamp),
            "recvWindow": recv_window,
            "signature_generated": signature is not None,
            "signature_redacted": None if signature is None else f"{signature[:6]}...REDACTED",
            "api_key_header_required": True,
            "credentials_complete": creds["credentials_complete"],
            "request_transmitted": False,
            "authenticated_transport_invoked": False,
        }

    def build_order_intent(
        self,
        intent_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        close_position: bool = False,
    ) -> dict[str, Any]:
        side = side.upper()
        order_type = order_type.upper()
        time_in_force = (time_in_force or self.config.order_intent_default_time_in_force).upper()
        if symbol != self.config.exchange_symbol:
            raise ValueError("symbol must be BTCUSDT")
        if side not in self.config.order_intent_allowed_sides:
            raise ValueError("side is not allowed")
        if order_type not in self.config.order_intent_allowed_types:
            raise ValueError("order type is not allowed")
        if float(quantity) <= 0 or float(quantity) > float(self.config.order_intent_max_quantity):
            raise ValueError("quantity is outside allowed range")
        if order_type == "LIMIT" and (price is None or float(price) <= 0):
            raise ValueError("LIMIT orders require positive price")
        if order_type == "MARKET" and price is not None:
            raise ValueError("MARKET order intent must not include price")
        if order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET") and (stop_price is None or float(stop_price) <= 0):
            raise ValueError(f"{order_type} requires positive stopPrice")
        if time_in_force not in ("GTC", "IOC", "FOK"):
            raise ValueError("timeInForce is invalid")
        if close_position and self.config.order_intent_require_reduce_only_for_close and not reduce_only:
            raise ValueError("close-position intents require reduceOnly")
        return {
            "intent_id": intent_id,
            "symbol": symbol,
            "side": side,
            "position_interpretation": "LONG" if side == "BUY" else "SHORT",
            "order_type": order_type,
            "quantity": float(quantity),
            "price": price,
            "stopPrice": stop_price,
            "timeInForce": time_in_force,
            "reduceOnly": bool(reduce_only),
            "closePosition": bool(close_position),
            "executable": False,
            "request_signed": False,
            "request_transmitted": False,
            "testnet_order_submitted": False,
            "exchange_order_id": None,
            "local_position_created": False,
            "futures_paper_state_mutated": False,
        }

    def submit_order(self, *args, **kwargs):
        return self._blocked("submit_order")

    def cancel_order(self, *args, **kwargs):
        return self._blocked("cancel_order")

    def fetch_account(self, *args, **kwargs):
        return self._blocked("fetch_account")

    def fetch_balances(self, *args, **kwargs):
        return self._blocked("fetch_balances")

    def fetch_positions(self, *args, **kwargs):
        return self._blocked("fetch_positions")

    def change_leverage(self, *args, **kwargs):
        return self._blocked("change_leverage")

    def change_margin_mode(self, *args, **kwargs):
        return self._blocked("change_margin_mode")

    def _blocked(self, operation: str):
        raise BinanceFuturesTestnetOperationBlocked(f"{self.BLOCKED_DECISION}: {operation}")

    def _public_get(self, path: str) -> BinancePublicResponse:
        if path not in self.config.allowed_public_paths:
            raise ValueError("public path is not allowed")
        url = f"{self.config.rest_base_url}{path}"
        last_error: Exception | None = None
        for _ in range(int(self.config.max_public_fetch_retries) + 1):
            try:
                response = self.http_get(url, int(self.config.request_timeout_seconds))
                final_host = urlparse(response.final_url).hostname
                if final_host != self.ALLOWED_HOST:
                    raise ValueError("final response host is not allowlisted")
                return response
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"public testnet request failed safely: {last_error}")

    def _default_http_get(self, url: str, timeout: int) -> BinancePublicResponse:
        request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Diagnostic"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact public testnet allowlist is validated before request.
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return BinancePublicResponse(status_code=int(response.status), final_url=response.geturl(), payload=payload)

    def validate_base_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme != "https":
            raise ValueError("base URL must use https")
        if parsed.username or parsed.password:
            raise ValueError("base URL must not include user info")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("base URL must not include path, query, or fragment")
        if host != self.ALLOWED_HOST:
            raise ValueError("base URL host is not the exact testnet allowlist")
        self._reject_ip_or_local(host)

    def _reject_ip_or_local(self, host: str | None) -> None:
        if not host or host in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("host is not allowed")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("IP-address hosts are not allowed")

    def _require_allowed_preview_path(self, path: str) -> None:
        blocked = ("/fapi/v1/order", "/fapi/v1/batchOrders", "/fapi/v1/allOpenOrders", "/fapi/v1/leverage", "/fapi/v1/marginType")
        if path in blocked or "listenKey" in path or path not in self.config.allowed_signed_preview_paths:
            raise ValueError("signed preview path is not allowed")

    def _canonical_query(self, parameters: dict[str, Any]) -> str:
        return urlencode(sorted((key, value) for key, value in parameters.items() if value is not None))
