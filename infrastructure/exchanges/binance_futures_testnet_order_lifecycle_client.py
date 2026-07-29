from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from models.binance_futures_testnet_order_lifecycle import (
    BinanceFuturesTestnetBookTicker,
    BinanceFuturesTestnetLifecycleCredentialMetadata,
    BinanceFuturesTestnetLifecycleExchangeFilters,
    BinanceFuturesTestnetLifecyclePreview,
    BinanceFuturesTestnetLifecycleRequestMetadata,
    BinanceFuturesTestnetOrderLifecycleConfig,
    BinanceFuturesTestnetOrderSummary,
)
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit_enforcement import LiveExecutionUnsignedMutationRequest


class BinanceFuturesTestnetLifecycleOperationBlocked(RuntimeError):
    pass


@dataclass
class BinanceLifecycleHTTPResponse:
    status_code: int
    final_url: str
    payload: Any
    response_bytes: int | None = None


class BinanceFuturesTestnetOrderLifecycleClient:
    ALLOWED_HOST = "demo-fapi.binance.com"
    ORDER_PATH = "/fapi/v1/order"
    SERVER_TIME_PATH = "/fapi/v1/time"
    EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
    BOOK_TICKER_PATH = "/fapi/v1/ticker/bookTicker"
    POSITION_MODE_PATH = "/fapi/v1/positionSide/dual"
    POSITION_RISK_PATH = "/fapi/v3/positionRisk"
    SAFE_CLIENT_ORDER_ID = re.compile(r"^[\.A-Z\:/a-z0-9_-]{1,36}$")
    GENERIC_CLIENT_ORDER_IDS = {"test", "order", "btc"}

    def __init__(
        self,
        config: BinanceFuturesTestnetOrderLifecycleConfig,
        http_get=None,
        authenticated_request=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
    ) -> None:
        self.config = config
        self.http_get = http_get or self._default_public_get
        self.authenticated_request = authenticated_request or self._default_authenticated_request
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.server_time_offset_ms: int | None = None
        self.validate_base_url(config.rest_base_url)

    def inspect_credentials(self) -> BinanceFuturesTestnetLifecycleCredentialMetadata:
        key = self.env.get(self.config.api_key_env_var)
        secret = self.env.get(self.config.api_secret_env_var)
        return BinanceFuturesTestnetLifecycleCredentialMetadata(
            api_key_present=bool(key),
            api_secret_present=bool(secret),
            api_key_length=len(key or ""),
            api_secret_length=len(secret or ""),
            credentials_complete=bool(key and secret),
            values_redacted=True,
        )

    def fetch_server_time(self) -> dict[str, Any]:
        response = self._public_get(self.config.server_time_path)
        if not isinstance(response.payload, dict) or not isinstance(response.payload.get("serverTime"), int):
            raise ValueError("serverTime payload is invalid")
        server_time = int(response.payload["serverTime"])
        local_time = self._now_ms()
        return {"server_time": server_time, "local_time": local_time, "clock_skew_ms": abs(local_time - server_time), "http_status": response.status_code}

    def set_server_time_offset(self, server_time: int, local_time: int | None = None) -> int:
        local = self._now_ms() if local_time is None else int(local_time)
        self.server_time_offset_ms = int(server_time) - local
        return self.server_time_offset_ms

    def fetch_exchange_filters(self) -> BinanceFuturesTestnetLifecycleExchangeFilters:
        response = self._public_get(self.config.exchange_info_path)
        return self.parse_exchange_filters(response.payload)

    def fetch_book_ticker(self) -> BinanceFuturesTestnetBookTicker:
        response = self._public_get(self.config.book_ticker_path, {"symbol": self.config.exchange_symbol})
        return self.parse_book_ticker(response.payload)

    def fetch_position_mode(self) -> bool:
        payload = self._signed_request("GET", self.config.position_mode_path, {})
        if not isinstance(payload, dict) or "dualSidePosition" not in payload:
            raise ValueError("position mode response is invalid")
        return str(payload["dualSidePosition"]).lower() == "true" if not isinstance(payload["dualSidePosition"], bool) else bool(payload["dualSidePosition"])

    def fetch_position_risk(self) -> list[dict[str, Any]]:
        payload = self._signed_request("GET", self.config.position_risk_path, {"symbol": self.config.exchange_symbol})
        if not isinstance(payload, list):
            raise ValueError("position risk response must be a list")
        return [row for row in payload if isinstance(row, dict) and row.get("symbol") == self.config.exchange_symbol]

    def require_zero_position(self, rows: list[dict[str, Any]]) -> bool:
        for row in rows:
            if _decimal(row.get("positionAmt", "0"), "positionAmt") != 0:
                raise ValueError("open BTCUSDT position detected")
        return True

    def parse_exchange_filters(self, payload: Any) -> BinanceFuturesTestnetLifecycleExchangeFilters:
        if not isinstance(payload, dict):
            raise ValueError("exchangeInfo response must be an object")
        symbols = payload.get("symbols")
        if not isinstance(symbols, list):
            raise ValueError("exchangeInfo symbols must be a list")
        symbol_payload = next((item for item in symbols if isinstance(item, dict) and item.get("symbol") == self.config.exchange_symbol), None)
        if symbol_payload is None:
            raise ValueError("BTCUSDT exchange filters were not found")
        filters = {item.get("filterType"): item for item in symbol_payload.get("filters", []) if isinstance(item, dict)}
        price_filter = filters.get("PRICE_FILTER") or {}
        lot_filter = filters.get("LOT_SIZE") or {}
        min_notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        parsed = BinanceFuturesTestnetLifecycleExchangeFilters(
            symbol=self.config.exchange_symbol,
            price_tick_size=_optional_decimal(price_filter.get("tickSize"), "tickSize"),
            min_price=_optional_decimal(price_filter.get("minPrice"), "minPrice"),
            max_price=_optional_decimal(price_filter.get("maxPrice"), "maxPrice"),
            lot_step_size=_optional_decimal(lot_filter.get("stepSize"), "stepSize"),
            min_qty=_optional_decimal(lot_filter.get("minQty"), "minQty"),
            max_qty=_optional_decimal(lot_filter.get("maxQty"), "maxQty"),
            min_notional=_optional_decimal(min_notional_filter.get("notional") or min_notional_filter.get("minNotional"), "minNotional"),
            raw_response_included=False,
        )
        if any(value is None for value in (parsed.price_tick_size, parsed.min_price, parsed.max_price, parsed.lot_step_size, parsed.min_qty, parsed.max_qty, parsed.min_notional)):
            raise ValueError("required exchange filters are missing")
        return parsed

    def parse_book_ticker(self, payload: Any) -> BinanceFuturesTestnetBookTicker:
        if not isinstance(payload, dict):
            raise ValueError("bookTicker response must be an object")
        if payload.get("symbol") != self.config.exchange_symbol:
            raise ValueError("bookTicker symbol is invalid")
        bid = _decimal(payload.get("bidPrice"), "bidPrice")
        ask = _decimal(payload.get("askPrice"), "askPrice")
        if bid <= 0 or ask <= 0 or ask <= bid:
            raise ValueError("bookTicker spread is invalid")
        return BinanceFuturesTestnetBookTicker(
            symbol=self.config.exchange_symbol,
            bid_price=bid,
            ask_price=ask,
            bid_qty=_optional_decimal(payload.get("bidQty"), "bidQty"),
            ask_qty=_optional_decimal(payload.get("askQty"), "askQty"),
        )

    def build_lifecycle_preview(
        self,
        lifecycle_id: str,
        client_order_id: str,
        side: str,
        quantity: float | Decimal | str,
        price_offset_bps: int | None = None,
        exchange_filters: BinanceFuturesTestnetLifecycleExchangeFilters | None = None,
        book_ticker: BinanceFuturesTestnetBookTicker | None = None,
    ) -> BinanceFuturesTestnetLifecyclePreview:
        self._validate_lifecycle_id(lifecycle_id)
        self._validate_client_order_id(client_order_id)
        side = side.upper()
        if side not in self.config.allowed_sides:
            raise ValueError("side must be BUY or SELL")
        quantity_decimal = _decimal(quantity, "quantity")
        offset = int(self.config.default_price_offset_bps if price_offset_bps is None else price_offset_bps)
        self._validate_quantity_and_offset(quantity_decimal, offset)
        derived_price = None
        estimated_notional = None
        filters_valid: bool | None = None
        non_marketable: bool | None = None
        if exchange_filters is not None and book_ticker is not None:
            derived_price = self.derive_post_only_price(side, book_ticker, exchange_filters, offset)
            estimated_notional = quantity_decimal * derived_price
            filters_valid = self.validate_filters_and_notional(quantity_decimal, derived_price, exchange_filters)
            non_marketable = self.validate_non_marketable(side, derived_price, book_ticker)
        return BinanceFuturesTestnetLifecyclePreview(
            lifecycle_id=lifecycle_id,
            client_order_id=client_order_id,
            symbol=self.config.exchange_symbol,
            side=side,
            order_type="LIMIT",
            time_in_force="GTX",
            quantity=quantity_decimal,
            price_offset_bps=offset,
            best_bid=None if book_ticker is None else book_ticker.bid_price,
            best_ask=None if book_ticker is None else book_ticker.ask_price,
            derived_price=derived_price,
            estimated_notional=estimated_notional,
            exchange_filters_valid=filters_valid,
            non_marketable_price_valid=non_marketable,
            post_only_valid=True,
            local_rules_valid=True,
            transmission_ready=filters_valid is True and non_marketable is True,
        )

    def derive_post_only_price(
        self,
        side: str,
        ticker: BinanceFuturesTestnetBookTicker,
        filters: BinanceFuturesTestnetLifecycleExchangeFilters,
        offset_bps: int,
    ) -> Decimal:
        if filters.price_tick_size is None:
            raise ValueError("price tick size is missing")
        offset = Decimal(offset_bps) / Decimal("10000")
        if side == "BUY":
            raw = ticker.bid_price * (Decimal("1") - offset)
            return _quantize_to_step(raw, filters.price_tick_size, ROUND_FLOOR)
        if side == "SELL":
            raw = ticker.ask_price * (Decimal("1") + offset)
            return _quantize_to_step(raw, filters.price_tick_size, ROUND_CEILING)
        raise ValueError("side must be BUY or SELL")

    def validate_non_marketable(self, side: str, price: Decimal, ticker: BinanceFuturesTestnetBookTicker) -> bool:
        if side == "BUY" and price < ticker.bid_price:
            return True
        if side == "SELL" and price > ticker.ask_price:
            return True
        raise ValueError("POST_ONLY_PRICE_UNSAFE")

    def validate_filters_and_notional(self, quantity: Decimal, price: Decimal, filters: BinanceFuturesTestnetLifecycleExchangeFilters) -> bool:
        required = (filters.price_tick_size, filters.min_price, filters.max_price, filters.lot_step_size, filters.min_qty, filters.max_qty, filters.min_notional)
        if any(item is None for item in required):
            raise ValueError("required exchange filters are missing")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if quantity < filters.min_qty:
            raise ValueError("quantity is below exchange minimum")
        if quantity > filters.max_qty or quantity > _decimal(self.config.maximum_quantity, "maximum_quantity"):
            raise ValueError("quantity is above maximum")
        if filters.lot_step_size > 0 and ((quantity - filters.min_qty) % filters.lot_step_size) != 0:
            raise ValueError("quantity does not satisfy exchange step size")
        if price < filters.min_price:
            raise ValueError("price is below exchange minimum")
        if filters.max_price > 0 and price > filters.max_price:
            raise ValueError("price is above exchange maximum")
        if filters.price_tick_size > 0 and ((price - filters.min_price) % filters.price_tick_size) != 0:
            raise ValueError("price does not satisfy exchange tick size")
        notional = quantity * price
        if notional < filters.min_notional:
            raise ValueError("estimated notional is below exchange minimum")
        if notional > _decimal(self.config.maximum_lifecycle_notional_usdt, "maximum_lifecycle_notional_usdt"):
            raise ValueError("estimated notional exceeds configured maximum")
        return True

    def build_create_unsigned_business_request(self, preview: BinanceFuturesTestnetLifecyclePreview) -> LiveExecutionUnsignedMutationRequest:
        self._require_transmission_ready(preview)
        params = self._canonical_order_parameters(preview)
        params["newOrderRespType"] = self.config.new_order_response_type
        return LiveExecutionUnsignedMutationRequest(
            operation=LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
            environment="TESTNET",
            symbol=self.config.exchange_symbol,
            subject_type="ORDER_LIFECYCLE",
            subject_id=preview.client_order_id,
            fingerprint_context={
                "schema_version": "1.0", "operation": "ORDER_LIFECYCLE_CREATE", "environment": "TESTNET", "symbol": self.config.exchange_symbol,
                "client_order_id": params["newClientOrderId"], "side": params["side"], "position_side": params["positionSide"],
                "order_type": params["type"], "quantity": str(params["quantity"]), "price": str(params["price"]),
                "time_in_force": params["timeInForce"], "reduce_only": str(params.get("reduceOnly", "false")).lower() == "true",
            },
            # newOrderRespType is a fixed config control, not caller input.
            transport_business_parameters=params,
        )

    def build_cancel_unsigned_business_request(self, client_order_id: str) -> LiveExecutionUnsignedMutationRequest:
        self._validate_client_order_id(client_order_id)
        params = {"symbol": self.config.exchange_symbol, "origClientOrderId": client_order_id}
        return LiveExecutionUnsignedMutationRequest(
            operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
            environment="TESTNET",
            symbol=self.config.exchange_symbol,
            subject_type="ORDER_LIFECYCLE",
            subject_id=client_order_id,
            fingerprint_context={
                "schema_version": "1.0", "operation": "ORDER_LIFECYCLE_CANCEL", "environment": "TESTNET", "symbol": self.config.exchange_symbol,
                "client_order_id": client_order_id,
            },
            transport_business_parameters=params,
        )

    def create_order(self, preview: BinanceFuturesTestnetLifecyclePreview, server_time: int | None = None, unsigned_business_request: dict[str, Any] | None = None) -> tuple[BinanceFuturesTestnetOrderSummary, BinanceFuturesTestnetLifecycleRequestMetadata]:
        self._require_transmission_ready(preview)
        params = self.build_create_unsigned_business_request(preview) if unsigned_business_request is None else dict(unsigned_business_request)
        payload, metadata = self._signed_request_with_metadata("POST", self.config.order_path, params)
        return self.sanitize_order_summary(payload, preview.client_order_id), metadata

    def query_order(self, client_order_id: str, server_time: int | None = None) -> tuple[BinanceFuturesTestnetOrderSummary, BinanceFuturesTestnetLifecycleRequestMetadata]:
        self._validate_client_order_id(client_order_id)
        last_error: Exception | None = None
        for retry in range(int(self.config.max_query_retries) + 1):
            try:
                payload, metadata = self._signed_request_with_metadata("GET", self.config.order_path, {"symbol": self.config.exchange_symbol, "origClientOrderId": client_order_id})
                metadata.retry_count = retry
                return self.sanitize_order_summary(payload, client_order_id), metadata
            except Exception as exc:
                last_error = exc
                if retry >= int(self.config.max_query_retries):
                    raise
        raise last_error or RuntimeError("query failed")

    def cancel_order_exact(self, client_order_id: str, server_time: int | None = None, unsigned_business_request: dict[str, Any] | None = None) -> tuple[BinanceFuturesTestnetOrderSummary, BinanceFuturesTestnetLifecycleRequestMetadata]:
        self._validate_client_order_id(client_order_id)
        params = self.build_cancel_unsigned_business_request(client_order_id) if unsigned_business_request is None else dict(unsigned_business_request)
        payload, metadata = self._signed_request_with_metadata("DELETE", self.config.order_path, params)
        return self.sanitize_order_summary(payload, client_order_id), metadata

    def sanitize_order_summary(self, payload: Any, client_order_id: str) -> BinanceFuturesTestnetOrderSummary:
        if not isinstance(payload, dict):
            raise ValueError("order response must be an object")
        return BinanceFuturesTestnetOrderSummary(
            symbol=str(payload.get("symbol") or self.config.exchange_symbol),
            client_order_id=str(payload.get("clientOrderId") or payload.get("origClientOrderId") or client_order_id),
            order_id=None if payload.get("orderId") is None else str(payload.get("orderId")),
            side=None if payload.get("side") is None else str(payload.get("side")),
            order_type=None if payload.get("type") is None else str(payload.get("type")),
            time_in_force=None if payload.get("timeInForce") is None else str(payload.get("timeInForce")),
            price=_optional_decimal(payload.get("price"), "price"),
            original_quantity=_optional_decimal(payload.get("origQty"), "origQty"),
            executed_quantity=_optional_decimal(payload.get("executedQty"), "executedQty") or Decimal("0"),
            status=None if payload.get("status") is None else str(payload.get("status")),
            raw_response_included=False,
        )

    def validate_base_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme != "https":
            raise ValueError("base URL must use https")
        if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("base URL must not include user info, path, query, or fragment")
        if host != self.ALLOWED_HOST:
            raise ValueError("base URL host is not the exact testnet allowlist")
        self._reject_ip_or_local(host)

    def submit_market_order(self, *args, **kwargs):
        return self._blocked("submit_market_order")

    def submit_conditional_order(self, *args, **kwargs):
        return self._blocked("submit_conditional_order")

    def submit_algo_order(self, *args, **kwargs):
        return self._blocked("submit_algo_order")

    def submit_batch_orders(self, *args, **kwargs):
        return self._blocked("submit_batch_orders")

    def modify_order(self, *args, **kwargs):
        return self._blocked("modify_order")

    def cancel_all_orders(self, *args, **kwargs):
        return self._blocked("cancel_all_orders")

    def fetch_open_orders(self, *args, **kwargs):
        return self._blocked("fetch_open_orders")

    def fetch_all_orders(self, *args, **kwargs):
        return self._blocked("fetch_all_orders")

    def fetch_trades(self, *args, **kwargs):
        return self._blocked("fetch_trades")

    def change_leverage(self, *args, **kwargs):
        return self._blocked("change_leverage")

    def change_margin_mode(self, *args, **kwargs):
        return self._blocked("change_margin_mode")

    def change_position_mode(self, *args, **kwargs):
        return self._blocked("change_position_mode")

    def change_multi_assets_mode(self, *args, **kwargs):
        return self._blocked("change_multi_assets_mode")

    def change_position_margin(self, *args, **kwargs):
        return self._blocked("change_position_margin")

    def close_position(self, *args, **kwargs):
        return self._blocked("close_position")

    def create_listen_key(self, *args, **kwargs):
        return self._blocked("create_listen_key")

    def open_user_stream(self, *args, **kwargs):
        return self._blocked("open_user_stream")

    def open_websocket(self, *args, **kwargs):
        return self._blocked("open_websocket")

    def _public_get(self, path: str, parameters: dict[str, Any] | None = None) -> BinanceLifecycleHTTPResponse:
        if path not in (self.SERVER_TIME_PATH, self.EXCHANGE_INFO_PATH, self.BOOK_TICKER_PATH):
            raise ValueError("public path is not allowed")
        url = f"{self.config.rest_base_url}{path}"
        if parameters:
            url = f"{url}?{urlencode(sorted(parameters.items()))}"
        response = self.http_get(url, int(self.config.request_timeout_seconds))
        if urlparse(response.final_url).hostname != self.ALLOWED_HOST:
            raise ValueError("final response host is not allowlisted")
        return response

    def _signed_request(self, method: str, path: str, parameters: dict[str, Any]) -> Any:
        payload, _ = self._signed_request_with_metadata(method, path, parameters)
        return payload

    def _signed_request_with_metadata(self, method: str, path: str, parameters: dict[str, Any]) -> tuple[Any, BinanceFuturesTestnetLifecycleRequestMetadata]:
        self._require_credentials()
        self._require_allowed_authenticated_transport(method, path)
        fresh_parameters = {
            key: value
            for key, value in parameters.items()
            if value is not None and key not in ("timestamp", "recvWindow", "signature")
        }
        fresh_parameters["timestamp"] = self._fresh_signed_timestamp_ms()
        fresh_parameters["recvWindow"] = int(self.config.recv_window_ms)
        canonical_parameters = {key: _format_decimal(value) if isinstance(value, Decimal) else value for key, value in fresh_parameters.items() if value is not None}
        canonical = urlencode(sorted(canonical_parameters.items()))
        signature = self._signature(canonical)
        request_parameters = {**canonical_parameters, "signature": signature}
        url = f"{self.config.rest_base_url}{path}"
        body = urlencode(sorted(request_parameters.items())).encode("utf-8")
        headers = {"X-MBX-APIKEY": self.env[self.config.api_key_env_var], "Content-Type": "application/x-www-form-urlencoded"}
        metadata = BinanceFuturesTestnetLifecycleRequestMetadata(
            method=method,
            host=self.ALLOWED_HOST,
            path=path,
            parameter_names=sorted(canonical_parameters.keys()),
            timestamp=int(canonical_parameters.get("timestamp", 0)),
            recv_window_ms=int(canonical_parameters.get("recvWindow", self.config.recv_window_ms)),
            signature_generated=True,
            signature_redacted=True,
            api_key_header_used=True,
        )
        response = self.authenticated_request(method, url, body, int(self.config.request_timeout_seconds), headers)
        if urlparse(response.final_url).hostname != self.ALLOWED_HOST:
            raise ValueError("final response host is not allowlisted")
        metadata.request_transmitted = True
        metadata.response_received = True
        metadata.response_status_code = int(response.status_code)
        metadata.final_host_validated = True
        return response.payload, metadata

    def _default_public_get(self, url: str, timeout: int) -> BinanceLifecycleHTTPResponse:
        request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Lifecycle"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact public testnet allowlist is validated.
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return BinanceLifecycleHTTPResponse(int(response.status), response.geturl(), payload, len(raw))

    def _default_authenticated_request(self, method: str, url: str, body: bytes, timeout: int, headers: dict[str, str]) -> BinanceLifecycleHTTPResponse:
        request = Request(url, data=body if method in ("POST", "DELETE") else None, method=method, headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Lifecycle", **headers})
        if method == "GET":
            url = f"{url}?{body.decode('utf-8')}"
            request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Lifecycle", **headers})
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact authenticated testnet allowlist is validated.
                raw = response.read()
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                return BinanceLifecycleHTTPResponse(int(response.status), response.geturl(), payload, len(raw))
        except HTTPError as exc:
            raw = exc.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {"code": exc.code}
            raise RuntimeError(_sanitize_error(payload.get("msg") or payload.get("code") or "Binance lifecycle request rejected")) from exc

    def _canonical_order_parameters(self, preview: BinanceFuturesTestnetLifecyclePreview) -> dict[str, Any]:
        if preview.derived_price is None:
            raise ValueError("derived price is required")
        return {
            "symbol": self.config.exchange_symbol,
            "side": preview.side,
            "type": "LIMIT",
            "timeInForce": "GTX",
            "quantity": _format_decimal(preview.quantity),
            "price": _format_decimal(preview.derived_price),
            "newClientOrderId": preview.client_order_id,
            "newOrderRespType": self.config.new_order_response_type,
            "positionSide": "BOTH",
        }

    def _require_allowed_authenticated_transport(self, method: str, path: str) -> None:
        if path in (self.config.position_mode_path, self.config.position_risk_path):
            if method != "GET":
                raise ValueError("position precheck endpoints are GET-only")
            return
        if method not in self.config.allowed_order_methods:
            raise ValueError("authenticated method is not allowlisted")
        if path != self.ORDER_PATH:
            raise ValueError("only exact order path is allowed")
        if self.config.order_path != self.ORDER_PATH:
            raise ValueError("order_path must be /fapi/v1/order")

    def _require_transmission_ready(self, preview: BinanceFuturesTestnetLifecyclePreview) -> None:
        if not preview.transmission_ready:
            raise ValueError("lifecycle preview is not transmission ready")
        if preview.order_type != "LIMIT" or preview.time_in_force != "GTX":
            raise ValueError("only LIMIT GTX can be transmitted")
        if preview.exchange_filters_valid is not True or preview.non_marketable_price_valid is not True:
            raise ValueError("filter and post-only price validation must pass")

    def _require_credentials(self) -> None:
        if not self.inspect_credentials().credentials_complete:
            raise ValueError("dedicated testnet credentials are incomplete")

    def _signature(self, canonical_query: str) -> str:
        secret = self.env.get(self.config.api_secret_env_var)
        if not secret:
            raise ValueError("dedicated testnet API secret is missing")
        return hmac.new(secret.encode("utf-8"), canonical_query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _fresh_signed_timestamp_ms(self) -> int:
        offset = 0 if self.server_time_offset_ms is None else int(self.server_time_offset_ms)
        return int(self._now_ms()) + offset

    def _validate_lifecycle_id(self, lifecycle_id: str) -> None:
        if not lifecycle_id or any(char.isspace() for char in lifecycle_id) or len(lifecycle_id) > 64:
            raise ValueError("lifecycle_id is invalid")

    def _validate_client_order_id(self, client_order_id: str) -> None:
        if not client_order_id or client_order_id.lower() in self.GENERIC_CLIENT_ORDER_IDS:
            raise ValueError("client order ID is too generic")
        if not client_order_id.startswith(self.config.client_order_id_prefix):
            raise ValueError("client order ID must use the configured lifecycle prefix")
        if len(client_order_id) > int(self.config.maximum_client_order_id_length):
            raise ValueError("client order ID exceeds maximum length")
        if any(char.isspace() for char in client_order_id) or not self.SAFE_CLIENT_ORDER_ID.match(client_order_id):
            raise ValueError("client order ID contains unsafe characters")

    def _validate_quantity_and_offset(self, quantity: Decimal, offset: int) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if quantity > _decimal(self.config.maximum_quantity, "maximum_quantity"):
            raise ValueError("quantity exceeds configured maximum")
        if offset < int(self.config.minimum_price_offset_bps) or offset > int(self.config.maximum_price_offset_bps):
            raise ValueError("price offset is outside the safe range")

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
        raise BinanceFuturesTestnetLifecycleOperationBlocked(f"OPERATION_BLOCKED: {operation}")


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


def _format_decimal(value: Decimal | float | str) -> str:
    decimal = value if isinstance(value, Decimal) else _decimal(value, "decimal")
    return format(decimal.normalize(), "f")


def _quantize_to_step(value: Decimal, step: Decimal, rounding) -> Decimal:
    if step <= 0:
        raise ValueError("step must be positive")
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step


def _sanitize_error(text: Any) -> str:
    message = str(text)
    for marker in ("signature=", "X-MBX-APIKEY", "apiKey"):
        if marker in message:
            return "redacted authenticated lifecycle error"
    return message[:180]
