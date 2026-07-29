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

from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectiveCredentialMetadata,
    BinanceFuturesTestnetProtectiveExchangeFilters,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    BinanceFuturesTestnetProtectivePosition,
    BinanceFuturesTestnetProtectivePreview,
    BinanceFuturesTestnetProtectiveRequestMetadata,
)
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit_enforcement import LiveExecutionUnsignedMutationRequest


class BinanceFuturesTestnetProtectiveOperationBlocked(RuntimeError):
    pass


@dataclass
class ProtectiveQueryPair:
    stop: BinanceFuturesTestnetProtectiveAlgoSummary
    take_profit: BinanceFuturesTestnetProtectiveAlgoSummary


class BinanceFuturesTestnetProtectiveAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        binance_code: int | None = None,
        method: str = "",
        path: str = "",
        request_transmitted: bool = False,
        response_received: bool = False,
        deterministic_rejection: bool = True,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.binance_code = binance_code
        self.sanitized_message = _sanitize_error(message)
        self.method = method
        self.path = path
        self.request_transmitted = request_transmitted
        self.response_received = response_received
        self.deterministic_rejection = deterministic_rejection


class BinanceFuturesTestnetProtectiveOrdersClient:
    ALLOWED_HOST = "demo-fapi.binance.com"
    SERVER_TIME_PATH = "/fapi/v1/time"
    EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
    POSITION_MODE_PATH = "/fapi/v1/positionSide/dual"
    POSITION_RISK_PATH = "/fapi/v3/positionRisk"
    ALGO_ORDER_PATH = "/fapi/v1/algoOrder"
    SAFE_CLIENT_ALGO_ID = re.compile(r"^[\.A-Z\:/a-z0-9_-]{1,36}$")
    TERMINAL_SAFE_STATUSES = {"CANCELED", "EXPIRED", "REJECTED"}
    TRIGGERED_STATUSES = {"TRIGGERED", "FILLED", "PARTIALLY_FILLED", "FINISHED"}

    def __init__(
        self,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
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
        self.server_time_synced_at_ms: int | None = None
        self.server_time_resync_count: int = 0
        self.validate_base_url(config.rest_base_url)

    def inspect_credentials(self) -> BinanceFuturesTestnetProtectiveCredentialMetadata:
        key = self.env.get(self.config.api_key_env_var)
        secret = self.env.get(self.config.api_secret_env_var)
        return BinanceFuturesTestnetProtectiveCredentialMetadata(
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
        return {"server_time": server_time, "local_time": local_time, "clock_skew_ms": abs(local_time - server_time)}

    def set_server_time_offset(self, server_time: int, local_time: int | None = None) -> int:
        local = self._now_ms() if local_time is None else int(local_time)
        self.server_time_offset_ms = int(server_time) - local
        self.server_time_synced_at_ms = local
        return self.server_time_offset_ms

    def synchronize_server_time(self, force: bool = False) -> bool:
        if not force and not self._server_time_sync_is_stale():
            return False
        server = self.fetch_server_time()
        if int(server["clock_skew_ms"]) > int(self.config.maximum_clock_skew_ms):
            raise ValueError("clock skew exceeds protective maximum")
        self.set_server_time_offset(int(server["server_time"]), int(server["local_time"]))
        self.server_time_resync_count += 1
        return True

    def fetch_exchange_filters(self) -> BinanceFuturesTestnetProtectiveExchangeFilters:
        return self.parse_exchange_filters(self._public_get(self.config.exchange_info_path).payload)

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

    def require_protectable_position(self, rows: list[dict[str, Any]]) -> BinanceFuturesTestnetProtectivePosition:
        relevant = [row for row in rows if _decimal(row.get("positionAmt", "0"), "positionAmt") != 0]
        if len(relevant) != 1:
            raise ValueError("exactly one non-zero BTCUSDT position is required")
        row = relevant[0]
        if "positionSide" not in row:
            raise ValueError("positionSide is required")
        if str(row.get("positionSide")) != self.config.required_position_side:
            raise ValueError("positionSide must be BOTH")
        amount = _decimal(row.get("positionAmt"), "positionAmt")
        entry = _decimal(row.get("entryPrice"), "entryPrice")
        mark = _decimal(row.get("markPrice"), "markPrice")
        notional = abs(_decimal(row.get("notional"), "notional")) if row.get("notional") is not None else abs(amount * mark)
        if abs(amount) > _decimal(self.config.maximum_position_abs_quantity, "maximum_position_abs_quantity"):
            raise ValueError("position quantity exceeds protective maximum")
        if notional > _decimal(self.config.maximum_position_notional_usdt, "maximum_position_notional_usdt"):
            raise ValueError("position notional exceeds protective maximum")
        if entry <= 0 or mark <= 0:
            raise ValueError("entryPrice and markPrice must be positive")
        return BinanceFuturesTestnetProtectivePosition(
            symbol=self.config.exchange_symbol,
            position_side="BOTH",
            position_amt=amount,
            entry_price=entry,
            mark_price=mark,
            notional=notional,
            direction="LONG" if amount > 0 else "SHORT",
        )

    def build_preview(
        self,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        position: BinanceFuturesTestnetProtectivePosition,
        filters: BinanceFuturesTestnetProtectiveExchangeFilters,
        stop_offset_bps: int | None = None,
        take_profit_offset_bps: int | None = None,
    ) -> BinanceFuturesTestnetProtectivePreview:
        self._validate_pair_id(pair_id)
        stop_client_algo_id = stop_client_algo_id or self.derive_client_algo_id(pair_id, "STOP", position.direction, position.mark_price)
        take_profit_client_algo_id = take_profit_client_algo_id or self.derive_client_algo_id(pair_id, "TAKE_PROFIT", position.direction, position.mark_price)
        self._validate_client_algo_id(stop_client_algo_id)
        self._validate_client_algo_id(take_profit_client_algo_id)
        if stop_client_algo_id == take_profit_client_algo_id:
            raise ValueError("protective clientAlgoIds must be distinct")
        stop_offset = int(self.config.default_stop_offset_bps if stop_offset_bps is None else stop_offset_bps)
        take_offset = int(self.config.default_take_profit_offset_bps if take_profit_offset_bps is None else take_profit_offset_bps)
        self._validate_offsets(stop_offset, take_offset)
        side = "SELL" if position.position_amt > 0 else "BUY"
        stop_trigger, take_trigger = self.derive_triggers(position, filters, stop_offset, take_offset)
        self.validate_trigger_order(position, stop_trigger, take_trigger, filters)
        return BinanceFuturesTestnetProtectivePreview(
            pair_id=pair_id,
            symbol=self.config.exchange_symbol,
            position_direction=position.direction,
            position_amount=position.position_amt,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            protective_side=side,
            stop_client_algo_id=stop_client_algo_id,
            take_profit_client_algo_id=take_profit_client_algo_id,
            stop_offset_bps=stop_offset,
            take_profit_offset_bps=take_offset,
            stop_trigger=stop_trigger,
            take_profit_trigger=take_trigger,
            transmission_ready=True,
        )


    def derive_client_algo_id(self, pair_id: str, label: str, position_direction: str, mark_price: Decimal) -> str:
        self._validate_pair_id(pair_id)
        suffix = "sl" if label == "STOP" else "tp" if label == "TAKE_PROFIT" else "xx"
        material = f"{self.config.exchange_symbol}|{pair_id}|{label}|{position_direction}|{_format_decimal(mark_price)}"
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
        client_algo_id = f"{self.config.client_algo_id_prefix}{suffix}-{digest}"
        self._validate_client_algo_id(client_algo_id)
        return client_algo_id

    def derive_triggers(
        self,
        position: BinanceFuturesTestnetProtectivePosition,
        filters: BinanceFuturesTestnetProtectiveExchangeFilters,
        stop_offset_bps: int,
        take_profit_offset_bps: int,
    ) -> tuple[Decimal, Decimal]:
        if filters.price_tick_size is None or filters.price_tick_size <= 0:
            raise ValueError("price tick size is missing")
        stop_offset = Decimal(stop_offset_bps) / Decimal("10000")
        take_offset = Decimal(take_profit_offset_bps) / Decimal("10000")
        if position.direction == "LONG":
            stop = _quantize_to_step(position.mark_price * (Decimal("1") - stop_offset), filters.price_tick_size, ROUND_FLOOR)
            take = _quantize_to_step(position.mark_price * (Decimal("1") + take_offset), filters.price_tick_size, ROUND_CEILING)
        elif position.direction == "SHORT":
            stop = _quantize_to_step(position.mark_price * (Decimal("1") + stop_offset), filters.price_tick_size, ROUND_CEILING)
            take = _quantize_to_step(position.mark_price * (Decimal("1") - take_offset), filters.price_tick_size, ROUND_FLOOR)
        else:
            raise ValueError("position direction is invalid")
        return stop, take

    def validate_trigger_order(
        self,
        position: BinanceFuturesTestnetProtectivePosition,
        stop_trigger: Decimal,
        take_profit_trigger: Decimal,
        filters: BinanceFuturesTestnetProtectiveExchangeFilters,
    ) -> bool:
        for name, price in (("stop_trigger", stop_trigger), ("take_profit_trigger", take_profit_trigger)):
            if price <= 0 or not price.is_finite():
                raise ValueError(f"{name} is invalid")
            if filters.min_price is not None and price < filters.min_price:
                raise ValueError(f"{name} is below exchange minimum")
            if filters.max_price is not None and filters.max_price > 0 and price > filters.max_price:
                raise ValueError(f"{name} is above exchange maximum")
        if position.direction == "LONG" and not (stop_trigger < position.mark_price < take_profit_trigger):
            raise ValueError("LONG protective triggers would immediately activate")
        if position.direction == "SHORT" and not (take_profit_trigger < position.mark_price < stop_trigger):
            raise ValueError("SHORT protective triggers would immediately activate")
        return True

    def build_create_unsigned_business_request(self, preview: BinanceFuturesTestnetProtectivePreview, label: str) -> LiveExecutionUnsignedMutationRequest:
        order_type = "STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET"
        trigger_price = preview.stop_trigger if label == "STOP" else preview.take_profit_trigger
        client_algo_id = preview.stop_client_algo_id if label == "STOP" else preview.take_profit_client_algo_id
        if not preview.transmission_ready or trigger_price is None:
            raise ValueError("protective preview is not transmission ready")
        if order_type not in self.config.allowed_order_types:
            raise ValueError("protective order type is not allowed")
        quantity = _format_decimal(abs(preview.position_amount))
        parameters = {
            "algoType": self.config.allowed_algo_type,
            "symbol": self.config.exchange_symbol,
            "side": preview.protective_side,
            "type": order_type,
            "triggerPrice": _format_decimal(trigger_price),
            "workingType": self.config.working_type,
            "closePosition": "true",
            "priceProtect": "true",
            "positionSide": self.config.required_position_side,
            "clientAlgoId": client_algo_id,
            "newOrderRespType": self.config.new_order_response_type,
        }
        return LiveExecutionUnsignedMutationRequest(
            operation=LiveExecutionOperation.PROTECTIVE_CREATE,
            environment="TESTNET",
            symbol=self.config.exchange_symbol,
            subject_type="PROTECTIVE_PAIR",
            subject_id=preview.pair_id,
            fingerprint_context={
                "schema_version": "1.0", "operation": "PROTECTIVE_CREATE", "environment": "TESTNET", "symbol": self.config.exchange_symbol,
                "pair_id": preview.pair_id, "leg_type": label, "side": preview.protective_side,
                "position_side": self.config.required_position_side, "quantity": quantity,
                "trigger_price": parameters["triggerPrice"], "close_position": True, "reduce_only": None,
                "client_algo_id": client_algo_id, "order_type": order_type, "working_type": self.config.working_type, "price_protect": True,
            },
            transport_business_parameters=parameters,
        )

    def build_cancel_unsigned_business_request(self, preview: BinanceFuturesTestnetProtectivePreview, label: str) -> LiveExecutionUnsignedMutationRequest:
        client_algo_id = preview.stop_client_algo_id if label == "STOP" else preview.take_profit_client_algo_id
        self._validate_client_algo_id(client_algo_id)
        parameters = {"symbol": self.config.exchange_symbol, "clientAlgoId": client_algo_id}
        return LiveExecutionUnsignedMutationRequest(
            operation=LiveExecutionOperation.PROTECTIVE_CANCEL,
            environment="TESTNET",
            symbol=self.config.exchange_symbol,
            subject_type="PROTECTIVE_PAIR",
            subject_id=preview.pair_id,
            fingerprint_context={
                "schema_version": "1.0", "operation": "PROTECTIVE_CANCEL", "environment": "TESTNET", "symbol": self.config.exchange_symbol,
                "pair_id": preview.pair_id, "leg_type": label, "client_algo_id": client_algo_id,
            },
            transport_business_parameters=parameters,
        )

    def create_stop_order(self, preview: BinanceFuturesTestnetProtectivePreview, unsigned_business_request: dict[str, Any] | None = None) -> tuple[BinanceFuturesTestnetProtectiveAlgoSummary, BinanceFuturesTestnetProtectiveRequestMetadata]:
        return self._create_algo_order(preview, "STOP_MARKET", preview.stop_trigger, preview.stop_client_algo_id, unsigned_business_request)

    def create_take_profit_order(self, preview: BinanceFuturesTestnetProtectivePreview, unsigned_business_request: dict[str, Any] | None = None) -> tuple[BinanceFuturesTestnetProtectiveAlgoSummary, BinanceFuturesTestnetProtectiveRequestMetadata]:
        return self._create_algo_order(preview, "TAKE_PROFIT_MARKET", preview.take_profit_trigger, preview.take_profit_client_algo_id, unsigned_business_request)

    def query_algo_order(self, client_algo_id: str) -> tuple[BinanceFuturesTestnetProtectiveAlgoSummary, BinanceFuturesTestnetProtectiveRequestMetadata]:
        self._validate_client_algo_id(client_algo_id)
        last_error: Exception | None = None
        timestamp_retry_count = 0
        for retry in range(int(self.config.max_query_retries) + 1):
            try:
                payload, metadata = self._signed_request_with_metadata("GET", self.config.algo_order_path, {"clientAlgoId": client_algo_id})
                metadata.retry_count = retry
                metadata.timestamp_retry_count = timestamp_retry_count
                metadata.timestamp_error_detected = timestamp_retry_count > 0
                return self.sanitize_algo_summary(payload, client_algo_id), metadata
            except BinanceFuturesTestnetProtectiveAPIError as exc:
                if exc.binance_code == -1021 and retry < int(self.config.max_query_retries):
                    timestamp_retry_count += 1
                    self.synchronize_server_time(force=True)
                    continue
                raise
            except (TimeoutError, OSError, ConnectionResetError) as exc:
                last_error = exc
                if retry >= int(self.config.max_query_retries):
                    raise
            except Exception:
                raise
        raise last_error or RuntimeError("query failed")

    def cancel_algo_order_exact(self, client_algo_id: str, unsigned_business_request: dict[str, Any] | None = None) -> tuple[BinanceFuturesTestnetProtectiveAlgoSummary, BinanceFuturesTestnetProtectiveRequestMetadata]:
        self._validate_client_algo_id(client_algo_id)
        params = {"clientAlgoId": client_algo_id} if unsigned_business_request is None else dict(unsigned_business_request)
        payload, metadata = self._signed_request_with_metadata("DELETE", self.config.algo_order_path, params)
        return self.sanitize_algo_summary(payload, client_algo_id), metadata

    def sanitize_algo_summary(self, payload: Any, client_algo_id: str) -> BinanceFuturesTestnetProtectiveAlgoSummary:
        if not isinstance(payload, dict):
            raise ValueError("algo order response must be an object")
        return BinanceFuturesTestnetProtectiveAlgoSummary(
            symbol=None if payload.get("symbol") in (None, "") else str(payload.get("symbol")),
            client_algo_id=None if payload.get("clientAlgoId") in (None, "") else str(payload.get("clientAlgoId")),
            algo_id=None if payload.get("algoId") is None else str(payload.get("algoId")),
            algo_type=None if payload.get("algoType") is None else str(payload.get("algoType")),
            side=None if payload.get("side") is None else str(payload.get("side")),
            position_side=None if payload.get("positionSide") is None else str(payload.get("positionSide")),
            order_type=None if (payload.get("orderType") or payload.get("type")) is None else str(payload.get("orderType") or payload.get("type")),
            trigger_price=_optional_decimal(payload.get("triggerPrice") or payload.get("stopPrice"), "triggerPrice"),
            algo_status=None if payload.get("algoStatus") is None else str(payload.get("algoStatus")),
            actual_order_id=None if payload.get("actualOrderId") in (None, "", 0, "0") else str(payload.get("actualOrderId")),
            executed_quantity=_optional_decimal(payload.get("actualQty") or payload.get("executedQty") or payload.get("executedQuantity"), "actualQty") or Decimal("0"),
            actual_price=_optional_decimal(payload.get("actualPrice"), "actualPrice"),
            close_position=_optional_bool(payload.get("closePosition")),
            working_type=None if payload.get("workingType") is None else str(payload.get("workingType")),
            price_protect=_optional_bool(payload.get("priceProtect")),
            response_code=_optional_int(payload.get("code")),
            response_message=None if payload.get("msg") is None else _sanitize_error(payload.get("msg")),
        )

    def validate_base_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme != "https" or host != self.ALLOWED_HOST or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("base URL must be exact Binance futures testnet host")
        self._reject_ip_or_local(host)

    def parse_exchange_filters(self, payload: Any) -> BinanceFuturesTestnetProtectiveExchangeFilters:
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ValueError("exchangeInfo response is invalid")
        symbol_payload = next((item for item in payload["symbols"] if isinstance(item, dict) and item.get("symbol") == self.config.exchange_symbol), None)
        if symbol_payload is None:
            raise ValueError("BTCUSDT exchange filters were not found")
        filters = {item.get("filterType"): item for item in symbol_payload.get("filters", []) if isinstance(item, dict)}
        price_filter = filters.get("PRICE_FILTER") or {}
        parsed = BinanceFuturesTestnetProtectiveExchangeFilters(
            symbol=self.config.exchange_symbol,
            price_tick_size=_optional_decimal(price_filter.get("tickSize"), "tickSize"),
            min_price=_optional_decimal(price_filter.get("minPrice"), "minPrice"),
            max_price=_optional_decimal(price_filter.get("maxPrice"), "maxPrice"),
        )
        if parsed.price_tick_size is None or parsed.min_price is None or parsed.max_price is None:
            raise ValueError("required PRICE_FILTER fields are missing")
        return parsed

    def _create_algo_order(
        self,
        preview: BinanceFuturesTestnetProtectivePreview,
        order_type: str,
        trigger_price: Decimal | None,
        client_algo_id: str,
        unsigned_business_request: dict[str, Any] | None = None,
    ) -> tuple[BinanceFuturesTestnetProtectiveAlgoSummary, BinanceFuturesTestnetProtectiveRequestMetadata]:
        params = self.build_create_unsigned_business_request(preview, "STOP" if order_type == "STOP_MARKET" else "TAKE_PROFIT") if unsigned_business_request is None else dict(unsigned_business_request)
        forbidden = {"pair_id", "leg", "quantity", "reduceOnly", "price", "priceMatch", "timeInForce", "callbackRate", "activatePrice", "goodTillDate", "selfTradePreventionMode"}
        if forbidden.intersection(params):
            raise ValueError("forbidden closePosition algo parameter present")
        payload, metadata = self._signed_request_with_metadata("POST", self.config.algo_order_path, params)
        return self.sanitize_algo_summary(payload, client_algo_id), metadata

    @staticmethod
    def _protective_exchange_params(unsigned_business_request: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in unsigned_business_request.items() if key not in {"pair_id", "leg", "quantity"}}

    def _public_get(self, path: str, parameters: dict[str, Any] | None = None) -> BinanceLifecycleHTTPResponse:
        if path not in (self.SERVER_TIME_PATH, self.EXCHANGE_INFO_PATH):
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

    def _signed_request_with_metadata(self, method: str, path: str, parameters: dict[str, Any]) -> tuple[Any, BinanceFuturesTestnetProtectiveRequestMetadata]:
        self._require_credentials()
        self._require_allowed_authenticated_transport(method, path)
        self.synchronize_server_time(force=self.server_time_offset_ms is None)
        fresh_parameters = {key: value for key, value in parameters.items() if value is not None and key not in ("timestamp", "recvWindow", "signature")}
        fresh_parameters["timestamp"] = self._fresh_signed_timestamp_ms()
        fresh_parameters["recvWindow"] = int(self.config.recv_window_ms)
        canonical_parameters = {key: _format_decimal(value) if isinstance(value, Decimal) else value for key, value in fresh_parameters.items() if value is not None}
        canonical = urlencode(sorted(canonical_parameters.items()))
        signature = self._signature(canonical)
        request_parameters = {**canonical_parameters, "signature": signature}
        url = f"{self.config.rest_base_url}{path}"
        body = urlencode(sorted(request_parameters.items())).encode("utf-8")
        headers = {"X-MBX-APIKEY": self.env[self.config.api_key_env_var], "Content-Type": "application/x-www-form-urlencoded"}
        metadata = BinanceFuturesTestnetProtectiveRequestMetadata(
            method=method,
            host=self.ALLOWED_HOST,
            path=path,
            parameter_names=sorted(canonical_parameters.keys()),
            timestamp=int(canonical_parameters.get("timestamp", 0)),
            recv_window_ms=int(canonical_parameters.get("recvWindow", self.config.recv_window_ms)),
            signature_generated=True,
            signature_redacted=True,
            api_key_header_used=True,
            server_time_sync_used=self.server_time_offset_ms is not None,
            server_time_resync_count=self.server_time_resync_count,
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
        request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Protective"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact public testnet allowlist is validated.
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return BinanceLifecycleHTTPResponse(int(response.status), response.geturl(), payload, len(raw))

    def _default_authenticated_request(self, method: str, url: str, body: bytes, timeout: int, headers: dict[str, str]) -> BinanceLifecycleHTTPResponse:
        request = Request(url, data=body if method in ("POST", "DELETE") else None, method=method, headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Protective", **headers})
        if method == "GET":
            request = Request(f"{url}?{body.decode('utf-8')}", method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-Protective", **headers})
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact authenticated testnet allowlist is validated.
                raw = response.read()
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                return BinanceLifecycleHTTPResponse(int(response.status), response.geturl(), payload, len(raw))
        except HTTPError as exc:
            raw = exc.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {"code": exc.code}
            code = _optional_int(payload.get("code"))
            message = payload.get("msg") or payload.get("code") or "Binance protective request rejected"
            raise BinanceFuturesTestnetProtectiveAPIError(
                _sanitize_error(message),
                http_status=int(exc.code),
                binance_code=code,
                method=method,
                path=self.ALGO_ORDER_PATH,
                request_transmitted=True,
                response_received=True,
                deterministic_rejection=True,
            ) from exc

    def _require_allowed_authenticated_transport(self, method: str, path: str) -> None:
        if path in (self.config.position_mode_path, self.config.position_risk_path):
            if method != "GET":
                raise ValueError("position precheck endpoints are GET-only")
            return
        if method not in self.config.allowed_methods:
            raise ValueError("authenticated method is not allowlisted")
        if path != self.ALGO_ORDER_PATH or self.config.algo_order_path != self.ALGO_ORDER_PATH:
            raise ValueError("only exact algoOrder path is allowed")

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

    def _server_time_sync_is_stale(self) -> bool:
        if self.server_time_synced_at_ms is None:
            return self.server_time_offset_ms is None
        return int(self._now_ms()) - int(self.server_time_synced_at_ms) > int(self.config.maximum_server_time_sync_age_ms)

    def _validate_pair_id(self, pair_id: str) -> None:
        if not pair_id or any(char.isspace() for char in pair_id) or len(pair_id) > 64:
            raise ValueError("pair_id is invalid")

    def _validate_client_algo_id(self, client_algo_id: str) -> None:
        if not client_algo_id or not client_algo_id.startswith(self.config.client_algo_id_prefix):
            raise ValueError("clientAlgoId must use the configured protective prefix")
        if len(client_algo_id) > int(self.config.maximum_client_algo_id_length):
            raise ValueError("clientAlgoId exceeds maximum length")
        if any(char.isspace() for char in client_algo_id) or not self.SAFE_CLIENT_ALGO_ID.match(client_algo_id):
            raise ValueError("clientAlgoId contains unsafe characters")

    def _validate_offsets(self, stop_offset_bps: int, take_profit_offset_bps: int) -> None:
        if stop_offset_bps < int(self.config.minimum_stop_offset_bps) or stop_offset_bps > int(self.config.maximum_stop_offset_bps):
            raise ValueError("stop offset is outside the safe range")
        if take_profit_offset_bps < int(self.config.minimum_take_profit_offset_bps) or take_profit_offset_bps > int(self.config.maximum_take_profit_offset_bps):
            raise ValueError("take-profit offset is outside the safe range")

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

    def cancel_all_orders(self, *args, **kwargs):
        raise BinanceFuturesTestnetProtectiveOperationBlocked("OPERATION_BLOCKED: cancel_all_orders")

    def fetch_open_algo_orders(self, *args, **kwargs):
        raise BinanceFuturesTestnetProtectiveOperationBlocked("OPERATION_BLOCKED: fetch_open_algo_orders")


def _optional_decimal(value: Any, name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value, name)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any, name: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not decimal.is_finite():
        raise ValueError(f"{name} must be finite")
    return decimal


def _quantize_to_step(value: Decimal, step: Decimal, rounding) -> Decimal:
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _sanitize_error(value: Any) -> str:
    text = str(value)
    for marker in ("signature=", "X-MBX-APIKEY", "BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"):
        if marker in text:
            return "redacted authenticated protective-order error"
    return text[:180]
