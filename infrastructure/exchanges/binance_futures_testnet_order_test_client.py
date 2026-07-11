from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from models.binance_futures_testnet_order_test import (
    BinanceFuturesTestnetExchangeFilterSummary,
    BinanceFuturesTestnetOrderTestConfig,
    BinanceFuturesTestnetOrderTestCredentialMetadata,
    BinanceFuturesTestnetOrderTestPreview,
    BinanceFuturesTestnetOrderTestRequestMetadata,
    OrderTestExchangeFilterValidationStatus,
    OrderTestNotionalValidationStatus,
    OrderTestReferencePriceSource,
)


class BinanceFuturesTestnetOrderOperationBlocked(RuntimeError):
    pass


@dataclass
class BinanceOrderTestHTTPResponse:
    status_code: int
    final_url: str
    payload: Any
    response_bytes: int | None = None


class BinanceFuturesTestnetOrderTestClient:
    ALLOWED_HOST = "demo-fapi.binance.com"
    TEST_ORDER_PATH = "/fapi/v1/order/test"
    ACTUAL_ORDER_PATH = "/fapi/v1/order"
    EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
    MARK_PRICE_PATH = "/fapi/v1/premiumIndex"
    SERVER_TIME_PATH = "/fapi/v1/time"
    SAFE_CLIENT_ORDER_ID = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(
        self,
        config: BinanceFuturesTestnetOrderTestConfig,
        http_get=None,
        authenticated_post=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
    ) -> None:
        self.config = config
        self.http_get = http_get or self._default_public_get
        self.authenticated_post = authenticated_post or self._default_authenticated_post
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.validate_base_url(config.rest_base_url)

    def inspect_credentials(self) -> BinanceFuturesTestnetOrderTestCredentialMetadata:
        key = self.env.get(self.config.api_key_env_var)
        secret = self.env.get(self.config.api_secret_env_var)
        return BinanceFuturesTestnetOrderTestCredentialMetadata(
            api_key_present=bool(key),
            api_secret_present=bool(secret),
            api_key_length=len(key or ""),
            api_secret_length=len(secret or ""),
            credentials_complete=bool(key and secret),
            values_redacted=True,
        )

    def fetch_server_time(self) -> dict[str, Any]:
        response = self._public_get(self.SERVER_TIME_PATH)
        if not isinstance(response.payload, dict) or not isinstance(response.payload.get("serverTime"), int):
            raise ValueError("serverTime payload is invalid")
        server_time = int(response.payload["serverTime"])
        local_time = self._now_ms()
        return {"server_time": server_time, "local_time": local_time, "clock_skew_ms": abs(local_time - server_time), "http_status": response.status_code}

    def fetch_exchange_filters(self) -> BinanceFuturesTestnetExchangeFilterSummary:
        response = self._public_get(self.EXCHANGE_INFO_PATH)
        return self.parse_exchange_filters(response.payload)

    def fetch_mark_price(self, symbol: str = "BTCUSDT") -> Decimal:
        if symbol != self.config.exchange_symbol:
            raise ValueError("Only BTCUSDT mark price may be requested")
        response = self._public_get(self.config.mark_price_path, {"symbol": symbol})
        if not isinstance(response.payload, dict):
            raise ValueError("mark price response must be an object")
        if response.payload.get("symbol") != symbol:
            raise ValueError("mark price response symbol is invalid")
        mark_price = _decimal(response.payload.get("markPrice"), "markPrice")
        if mark_price <= 0 or (mark_price == 0 and not self.config.allow_zero_market_reference_price):
            raise ValueError("mark price must be positive")
        return mark_price

    def parse_exchange_filters(self, payload: Any) -> BinanceFuturesTestnetExchangeFilterSummary:
        if not isinstance(payload, dict):
            raise ValueError("exchangeInfo response must be an object")
        symbols = payload.get("symbols")
        if not isinstance(symbols, list):
            raise ValueError("exchangeInfo symbols must be a list")
        symbol_payload = next((item for item in symbols if isinstance(item, dict) and item.get("symbol") == self.config.exchange_symbol), None)
        if symbol_payload is None:
            raise ValueError("BTCUSDT exchange filters were not found")
        filters = {item.get("filterType"): item for item in symbol_payload.get("filters", []) if isinstance(item, dict)}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_filter = filters.get("LOT_SIZE", {})
        market_lot_filter = filters.get("MARKET_LOT_SIZE", {})
        min_notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        return BinanceFuturesTestnetExchangeFilterSummary(
            symbol=self.config.exchange_symbol,
            price_tick_size=_optional_decimal(price_filter.get("tickSize"), "tickSize"),
            min_price=_optional_decimal(price_filter.get("minPrice"), "minPrice"),
            max_price=_optional_decimal(price_filter.get("maxPrice"), "maxPrice"),
            lot_step_size=_optional_decimal(lot_filter.get("stepSize"), "stepSize"),
            min_qty=_optional_decimal(lot_filter.get("minQty"), "minQty"),
            max_qty=_optional_decimal(lot_filter.get("maxQty"), "maxQty"),
            market_lot_step_size=_optional_decimal(market_lot_filter.get("stepSize"), "marketStepSize"),
            market_min_qty=_optional_decimal(market_lot_filter.get("minQty"), "marketMinQty"),
            market_max_qty=_optional_decimal(market_lot_filter.get("maxQty"), "marketMaxQty"),
            min_notional=_optional_decimal(min_notional_filter.get("notional") or min_notional_filter.get("minNotional"), "minNotional"),
            raw_response_included=False,
        )

    def build_order_test_preview(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        quantity: float | Decimal | str,
        price: float | Decimal | str | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        exchange_filters: BinanceFuturesTestnetExchangeFilterSummary | None = None,
        mark_price: float | Decimal | str | None = None,
        **forbidden,
    ) -> BinanceFuturesTestnetOrderTestPreview:
        if forbidden:
            raise ValueError(f"conditional or unsupported parameters are forbidden: {', '.join(sorted(forbidden))}")
        side = side.upper()
        order_type = order_type.upper()
        time_in_force = time_in_force.upper() if time_in_force else None
        if side not in self.config.allowed_sides:
            raise ValueError("side must be BUY or SELL")
        if order_type not in self.config.allowed_order_types:
            raise ValueError("order_type must be MARKET or LIMIT")
        quantity_decimal = _decimal(quantity, "quantity")
        price_decimal = None if price is None else _decimal(price, "price")
        mark_price_decimal = None if mark_price is None else _decimal(mark_price, "markPrice")
        if quantity_decimal <= 0:
            raise ValueError("quantity must be positive")
        if quantity_decimal > _decimal(self.config.maximum_quantity, "maximum_quantity"):
            raise ValueError("quantity exceeds configured maximum")
        self._validate_client_order_id(client_order_id)
        if not isinstance(reduce_only, bool):
            raise ValueError("reduce_only must be boolean")
        if order_type == "MARKET":
            if price_decimal is not None:
                raise ValueError("MARKET test order preview must not include price")
            if time_in_force is not None:
                raise ValueError("MARKET test order preview must not include timeInForce")
        if order_type == "LIMIT":
            if price_decimal is None or price_decimal <= 0:
                raise ValueError("LIMIT test order preview requires positive price")
            if time_in_force not in self.config.allowed_time_in_force:
                raise ValueError("LIMIT test order preview requires GTC, IOC, or FOK")
        reference_price = price_decimal if order_type == "LIMIT" else mark_price_decimal
        estimated_notional = quantity_decimal * reference_price if reference_price is not None else None
        configured_max_valid = None
        if estimated_notional is not None:
            configured_max_valid = estimated_notional <= _decimal(self.config.maximum_test_notional_usdt, "maximum_test_notional_usdt")
        if configured_max_valid is False:
            raise ValueError("estimated notional exceeds configured maximum")
        notional_status = OrderTestNotionalValidationStatus.NOT_EVALUATED.value
        exchange_filter_status = OrderTestExchangeFilterValidationStatus.NOT_EVALUATED.value
        exchange_filters_valid: bool | None = None
        exchange_min_notional_valid: bool | None = None
        transmission_ready = False
        if exchange_filters and self.config.require_exchange_filter_validation:
            exchange_min_notional_valid = self._validate_notional(estimated_notional, exchange_filters)
            exchange_filters_valid = self._validate_filters(order_type, quantity_decimal, price_decimal, exchange_filters)
            notional_status = OrderTestNotionalValidationStatus.PASS.value
            exchange_filter_status = OrderTestExchangeFilterValidationStatus.PASS.value
            transmission_ready = all((exchange_filters_valid, configured_max_valid, exchange_min_notional_valid))
        elif order_type == "LIMIT" and estimated_notional is not None:
            notional_status = OrderTestNotionalValidationStatus.NOT_EVALUATED.value
        parameter_names = sorted(self._canonical_order_parameters(client_order_id, side, order_type, quantity_decimal, price_decimal, time_in_force, reduce_only, timestamp=0, include_timestamp=False).keys())
        return BinanceFuturesTestnetOrderTestPreview(
            client_order_id=client_order_id,
            symbol=self.config.exchange_symbol,
            side=side,
            order_type=order_type,
            quantity=quantity_decimal,
            price=price_decimal,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            reference_price=reference_price,
            reference_price_source=OrderTestReferencePriceSource.MARK_PRICE.value if order_type == "MARKET" and reference_price is not None else None,
            estimated_notional=estimated_notional,
            configured_max_notional_valid=configured_max_valid,
            exchange_min_notional_valid=exchange_min_notional_valid,
            notional_validation_status=notional_status,
            exchange_filter_validation_status=exchange_filter_status,
            exchange_filters_valid=exchange_filters_valid,
            local_rules_valid=True,
            transmission_ready=transmission_ready,
            executable=False,
            parameter_names=parameter_names,
        )

    def submit_test_order(
        self,
        preview: BinanceFuturesTestnetOrderTestPreview,
        server_time: int | None = None,
    ) -> BinanceFuturesTestnetOrderTestRequestMetadata:
        self._require_allowed_test_order_transport()
        self._require_credentials()
        self._require_transmission_ready(preview)
        timestamp = int(server_time if server_time is not None else self._now_ms())
        recv_window = int(self.config.recv_window_ms)
        parameters = self._canonical_order_parameters(
            preview.client_order_id,
            preview.side,
            preview.order_type,
            preview.quantity,
            preview.price,
            preview.time_in_force,
            preview.reduce_only,
            timestamp=timestamp,
            include_timestamp=True,
        )
        parameters["recvWindow"] = recv_window
        canonical = self._canonical_query(parameters)
        signature = self._signature(canonical)
        request_parameters = {**parameters, "signature": signature}
        url = f"{self.config.rest_base_url}{self.TEST_ORDER_PATH}"
        body = self._canonical_query(request_parameters).encode("utf-8")
        headers = {"X-MBX-APIKEY": self.env[self.config.api_key_env_var], "Content-Type": "application/x-www-form-urlencoded"}
        metadata = BinanceFuturesTestnetOrderTestRequestMetadata(
            method="POST",
            host=self.ALLOWED_HOST,
            path=self.TEST_ORDER_PATH,
            parameter_names=sorted(parameters.keys()),
            timestamp=timestamp,
            recv_window_ms=recv_window,
            signature_generated=True,
            signature_redacted=True,
            api_key_header_used=True,
        )
        response = self.authenticated_post(url, body, int(self.config.request_timeout_seconds), headers)
        if urlparse(response.final_url).hostname != self.ALLOWED_HOST:
            raise ValueError("final response host is not allowlisted")
        if not (response.payload == {} or response.payload is None):
            raise ValueError("test order response must be an empty object")
        metadata.request_transmitted = True
        metadata.response_received = True
        metadata.response_status_code = int(response.status_code)
        metadata.final_host_validated = True
        metadata.response_empty_object = True
        metadata.retry_count = 0
        return metadata

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

    def submit_actual_order(self, *args, **kwargs):
        return self._blocked("submit_actual_order")

    def submit_algo_order(self, *args, **kwargs):
        return self._blocked("submit_algo_order")

    def cancel_order(self, *args, **kwargs):
        return self._blocked("cancel_order")

    def modify_order(self, *args, **kwargs):
        return self._blocked("modify_order")

    def fetch_order(self, *args, **kwargs):
        return self._blocked("fetch_order")

    def fetch_open_orders(self, *args, **kwargs):
        return self._blocked("fetch_open_orders")

    def fetch_trades(self, *args, **kwargs):
        return self._blocked("fetch_trades")

    def change_leverage(self, *args, **kwargs):
        return self._blocked("change_leverage")

    def change_margin_mode(self, *args, **kwargs):
        return self._blocked("change_margin_mode")

    def change_position_mode(self, *args, **kwargs):
        return self._blocked("change_position_mode")

    def change_position_margin(self, *args, **kwargs):
        return self._blocked("change_position_margin")

    def create_listen_key(self, *args, **kwargs):
        return self._blocked("create_listen_key")

    def open_user_stream(self, *args, **kwargs):
        return self._blocked("open_user_stream")

    def open_websocket(self, *args, **kwargs):
        return self._blocked("open_websocket")

    def _public_get(self, path: str, parameters: dict[str, Any] | None = None) -> BinanceOrderTestHTTPResponse:
        if path not in (self.SERVER_TIME_PATH, self.EXCHANGE_INFO_PATH, self.MARK_PRICE_PATH):
            raise ValueError("public path is not allowed")
        url = f"{self.config.rest_base_url}{path}"
        if parameters:
            url = f"{url}?{urlencode(sorted(parameters.items()))}"
        response = self.http_get(url, int(self.config.request_timeout_seconds))
        if urlparse(response.final_url).hostname != self.ALLOWED_HOST:
            raise ValueError("final response host is not allowlisted")
        return response

    def _default_public_get(self, url: str, timeout: int) -> BinanceOrderTestHTTPResponse:
        request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-OrderTest"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact public testnet allowlist is validated.
            body = response.read()
            payload = json.loads(body.decode("utf-8")) if body else {}
            return BinanceOrderTestHTTPResponse(int(response.status), response.geturl(), payload, len(body))

    def _default_authenticated_post(self, url: str, body: bytes, timeout: int, headers: dict[str, str]) -> BinanceOrderTestHTTPResponse:
        request = Request(url, data=body, method="POST", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-OrderTest", **headers})
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact authenticated testnet allowlist is validated.
                raw = response.read()
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                return BinanceOrderTestHTTPResponse(int(response.status), response.geturl(), payload, len(raw))
        except HTTPError as exc:
            raw = exc.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {"code": exc.code}
            message = str(payload.get("msg") or payload.get("code") or "Binance test order rejected")
            raise RuntimeError(_sanitize_error(message)) from exc

    def _canonical_order_parameters(self, client_order_id: str, side: str, order_type: str, quantity: Decimal, price: Decimal | None, time_in_force: str | None, reduce_only: bool, timestamp: int, include_timestamp: bool) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "symbol": self.config.exchange_symbol,
            "side": side,
            "type": order_type,
            "quantity": _format_decimal(quantity),
            "newClientOrderId": client_order_id,
        }
        if price is not None:
            parameters["price"] = _format_decimal(price)
        if time_in_force is not None:
            parameters["timeInForce"] = time_in_force
        if reduce_only:
            parameters["reduceOnly"] = "true"
        if include_timestamp:
            parameters["timestamp"] = timestamp
        return parameters

    def _require_allowed_test_order_transport(self) -> None:
        if self.config.allowed_http_methods != ["POST"]:
            raise ValueError("Only POST is allowlisted for test order transport")
        if self.config.test_order_path != self.TEST_ORDER_PATH:
            raise ValueError("test order path must be /fapi/v1/order/test")
        if self.config.allowed_authenticated_paths != [self.TEST_ORDER_PATH]:
            raise ValueError("Only /fapi/v1/order/test may be authenticated")
        if self.ACTUAL_ORDER_PATH in self.config.allowed_authenticated_paths:
            raise ValueError("actual order endpoint is forbidden")

    def _require_transmission_ready(self, preview: BinanceFuturesTestnetOrderTestPreview) -> None:
        if not preview.transmission_ready:
            raise ValueError("order-test preview is not transmission ready")
        if preview.exchange_filters_valid is not True:
            raise ValueError("exchange filters were not validated")
        if preview.exchange_filter_validation_status != OrderTestExchangeFilterValidationStatus.PASS.value:
            raise ValueError("exchange filter validation did not pass")
        if preview.notional_validation_status != OrderTestNotionalValidationStatus.PASS.value:
            raise ValueError("notional validation did not pass")
        if preview.configured_max_notional_valid is not True or preview.exchange_min_notional_valid is not True:
            raise ValueError("notional guard did not pass")

    def _require_credentials(self) -> None:
        if not self.inspect_credentials().credentials_complete:
            raise ValueError("dedicated testnet credentials are incomplete")

    def _signature(self, canonical_query: str) -> str:
        secret = self.env.get(self.config.api_secret_env_var)
        if not secret:
            raise ValueError("dedicated testnet API secret is missing")
        return hmac.new(secret.encode("utf-8"), canonical_query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _canonical_query(self, parameters: dict[str, Any]) -> str:
        return urlencode(sorted((key, value) for key, value in parameters.items() if value is not None))

    def _validate_client_order_id(self, client_order_id: str) -> None:
        if not client_order_id.startswith(self.config.client_order_id_prefix):
            raise ValueError("client order ID must use the configured test prefix")
        if len(client_order_id) > int(self.config.maximum_client_order_id_length):
            raise ValueError("client order ID exceeds maximum length")
        if not self.SAFE_CLIENT_ORDER_ID.match(client_order_id):
            raise ValueError("client order ID contains unsafe characters")

    def _validate_filters(self, order_type: str, quantity: Decimal, price: Decimal | None, filters: BinanceFuturesTestnetExchangeFilterSummary) -> bool:
        min_qty = filters.market_min_qty if order_type == "MARKET" and filters.market_min_qty is not None else filters.min_qty
        max_qty = filters.market_max_qty if order_type == "MARKET" and filters.market_max_qty is not None else filters.max_qty
        step = filters.market_lot_step_size if order_type == "MARKET" and filters.market_lot_step_size is not None else filters.lot_step_size
        if min_qty is None or max_qty is None or step is None:
            raise ValueError("required quantity filters are missing")
        if min_qty is not None and quantity < min_qty:
            raise ValueError("quantity is below exchange minimum")
        if max_qty is not None and quantity > max_qty:
            raise ValueError("quantity is above exchange maximum")
        if step > 0 and ((quantity - min_qty) % step) != 0:
            raise ValueError("quantity does not satisfy exchange step size")
        if price is not None:
            if filters.price_tick_size is None or filters.min_price is None:
                raise ValueError("required price filters are missing")
            if filters.min_price is not None and price < filters.min_price:
                raise ValueError("price is below exchange minimum")
            if filters.max_price is not None and filters.max_price > 0 and price > filters.max_price:
                raise ValueError("price is above exchange maximum")
            if filters.price_tick_size > 0 and ((price - filters.min_price) % filters.price_tick_size) != 0:
                raise ValueError("price does not satisfy exchange tick size")
        return True

    def _validate_notional(self, estimated_notional: Decimal | None, filters: BinanceFuturesTestnetExchangeFilterSummary) -> bool:
        if estimated_notional is None:
            raise ValueError("notional was not evaluated")
        if estimated_notional > _decimal(self.config.maximum_test_notional_usdt, "maximum_test_notional_usdt"):
            raise ValueError("estimated notional exceeds configured maximum")
        if filters.min_notional is None:
            raise ValueError("exchange minimum notional filter is missing")
        if estimated_notional < filters.min_notional:
            raise ValueError("estimated notional is below exchange minimum")
        return True

    def _reject_ip_or_local(self, host: str | None) -> None:
        if not host or host in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("host is not allowed")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("IP-address hosts are not allowed")

    def _now_ms(self) -> int:
        if self.now_ms_provider is not None:
            return int(self.now_ms_provider())
        return int(time.time() * 1000)

    def _blocked(self, operation: str):
        raise BinanceFuturesTestnetOrderOperationBlocked(f"ACTUAL_ORDER_OPERATION_BLOCKED: {operation}")


def _optional_decimal(value: Any, name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value, name)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} is not a valid decimal") from exc
    if not decimal.is_finite():
        raise ValueError(f"{name} must be finite")
    return decimal


def _format_decimal(value: Decimal | float) -> str:
    decimal = value if isinstance(value, Decimal) else _decimal(value, "decimal")
    return format(decimal.normalize(), "f")


def _sanitize_error(text: Any) -> str:
    message = str(text)
    for marker in ("signature=", "X-MBX-APIKEY", "apiKey"):
        if marker in message:
            return "redacted authenticated test order error"
    return message[:180]
