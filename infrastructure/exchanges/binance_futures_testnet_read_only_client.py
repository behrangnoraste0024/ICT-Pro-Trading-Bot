from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from models.binance_futures_testnet_read_only import (
    BinanceFuturesTestnetAccountSummary,
    BinanceFuturesTestnetAuthenticatedRequestMetadata,
    BinanceFuturesTestnetBalanceSummary,
    BinanceFuturesTestnetCredentialMetadata,
    BinanceFuturesTestnetPositionSummary,
    BinanceFuturesTestnetReadOnlyConfig,
)


class BinanceFuturesTestnetReadOnlyOperationBlocked(RuntimeError):
    pass


@dataclass
class BinanceReadOnlyHTTPResponse:
    status_code: int
    final_url: str
    payload: Any
    response_bytes: int | None = None


class BinanceFuturesTestnetReadOnlyClient:
    ALLOWED_HOST = "demo-fapi.binance.com"
    ALLOWED_AUTH_PATHS = {"/fapi/v3/account", "/fapi/v3/balance", "/fapi/v3/positionRisk"}
    BLOCKED_DECISION = "AUTHENTICATED_READ_ONLY_OPERATION_BLOCKED"

    def __init__(
        self,
        config: BinanceFuturesTestnetReadOnlyConfig,
        http_get=None,
        authenticated_get=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
    ) -> None:
        self.config = config
        self.http_get = http_get or self._default_public_get
        self.authenticated_get = authenticated_get or self._default_authenticated_get
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.validate_base_url(config.rest_base_url)

    def inspect_credential_presence(self) -> BinanceFuturesTestnetCredentialMetadata:
        api_key = self.env.get(self.config.api_key_env_var)
        api_secret = self.env.get(self.config.api_secret_env_var)
        return BinanceFuturesTestnetCredentialMetadata(
            api_key_present=bool(api_key),
            api_secret_present=bool(api_secret),
            api_key_length=len(api_key or ""),
            api_secret_length=len(api_secret or ""),
            credentials_complete=bool(api_key and api_secret),
            credential_source=self.config.credential_source,
            values_redacted=True,
        )

    def fetch_server_time(self) -> dict[str, Any]:
        response = self._public_get(self.config.server_time_path)
        if not isinstance(response.payload, dict) or not isinstance(response.payload.get("serverTime"), int):
            raise ValueError("serverTime payload is invalid")
        local_time = self._now_ms()
        server_time = int(response.payload["serverTime"])
        return {
            "server_time": server_time,
            "local_time": local_time,
            "clock_skew_ms": abs(local_time - server_time),
            "http_status": response.status_code,
            "final_host": urlparse(response.final_url).hostname,
        }

    def fetch_account(self, server_time: int | None = None) -> tuple[BinanceFuturesTestnetAccountSummary, BinanceFuturesTestnetAuthenticatedRequestMetadata]:
        response, metadata = self._authenticated_get(self.config.account_path, {}, server_time)
        return self.parse_account_summary(response.payload), metadata

    def fetch_balance(self, asset: str = "USDT", server_time: int | None = None) -> tuple[BinanceFuturesTestnetBalanceSummary, BinanceFuturesTestnetAuthenticatedRequestMetadata]:
        if asset != self.config.balance_asset_filter:
            raise ValueError("Only USDT balance may be requested")
        response, metadata = self._authenticated_get(self.config.balance_path, {}, server_time)
        return self.parse_balance_summary(response.payload, asset), metadata

    def fetch_position_risk(self, symbol: str = "BTCUSDT", server_time: int | None = None) -> tuple[BinanceFuturesTestnetPositionSummary, BinanceFuturesTestnetAuthenticatedRequestMetadata]:
        if symbol != self.config.position_symbol_filter:
            raise ValueError("Only BTCUSDT position risk may be requested")
        response, metadata = self._authenticated_get(self.config.position_risk_path, {"symbol": symbol}, server_time)
        return self.parse_position_summary(response.payload, symbol), metadata

    def parse_account_summary(self, payload: Any) -> BinanceFuturesTestnetAccountSummary:
        if not isinstance(payload, dict):
            raise ValueError("account response must be an object")
        return BinanceFuturesTestnetAccountSummary(
            fee_tier=_optional_int(payload.get("feeTier")),
            can_trade=_optional_bool(payload.get("canTrade")),
            can_deposit=_optional_bool(payload.get("canDeposit")),
            can_withdraw=_optional_bool(payload.get("canWithdraw")),
            update_time=_optional_int(payload.get("updateTime")),
            multi_assets_margin=_optional_bool(payload.get("multiAssetsMargin")),
            total_initial_margin=_optional_float(payload.get("totalInitialMargin")),
            total_maintenance_margin=_optional_float(payload.get("totalMaintMargin")),
            total_wallet_balance=_optional_float(payload.get("totalWalletBalance")),
            total_unrealized_profit=_optional_float(payload.get("totalUnrealizedProfit")),
            total_margin_balance=_optional_float(payload.get("totalMarginBalance")),
            total_position_initial_margin=_optional_float(payload.get("totalPositionInitialMargin")),
            total_open_order_initial_margin=_optional_float(payload.get("totalOpenOrderInitialMargin")),
            total_cross_wallet_balance=_optional_float(payload.get("totalCrossWalletBalance")),
            total_cross_unrealized_pnl=_optional_float(payload.get("totalCrossUnPnl")),
            available_balance=_optional_float(payload.get("availableBalance")),
            max_withdraw_amount=_optional_float(payload.get("maxWithdrawAmount")),
            asset_count=len(payload.get("assets") or []),
            position_count=len(payload.get("positions") or []),
            raw_response_included=False,
        )

    def parse_balance_summary(self, payload: Any, asset: str = "USDT") -> BinanceFuturesTestnetBalanceSummary:
        if not isinstance(payload, list):
            raise ValueError("balance response must be a list")
        row = next((item for item in payload if isinstance(item, dict) and item.get("asset") == asset), None)
        if row is None:
            if self.config.include_zero_balance_asset:
                return BinanceFuturesTestnetBalanceSummary(asset=asset)
            raise ValueError(f"{asset} balance was not found")
        return BinanceFuturesTestnetBalanceSummary(
            asset=asset,
            account_alias_present=bool(row.get("accountAlias")),
            wallet_balance=_required_float(row.get("balance"), "balance"),
            cross_wallet_balance=_required_float(row.get("crossWalletBalance"), "crossWalletBalance"),
            cross_unrealized_pnl=_required_float(row.get("crossUnPnl"), "crossUnPnl"),
            available_balance=_required_float(row.get("availableBalance"), "availableBalance"),
            max_withdraw_amount=_required_float(row.get("maxWithdrawAmount"), "maxWithdrawAmount"),
            margin_available=_optional_bool(row.get("marginAvailable")),
            update_time=_optional_int(row.get("updateTime")),
            raw_response_included=False,
        )

    def parse_position_summary(self, payload: Any, symbol: str = "BTCUSDT") -> BinanceFuturesTestnetPositionSummary:
        if not isinstance(payload, list):
            raise ValueError("positionRisk response must be a list")
        row = next((item for item in payload if isinstance(item, dict) and item.get("symbol") == symbol), None)
        if row is None:
            if self.config.include_zero_position:
                return BinanceFuturesTestnetPositionSummary(symbol=symbol)
            raise ValueError(f"{symbol} position risk was not found")
        amount = _required_float(row.get("positionAmt"), "positionAmt")
        return BinanceFuturesTestnetPositionSummary(
            symbol=symbol,
            position_side=str(row.get("positionSide") or "BOTH"),
            position_amount=amount,
            has_open_position=abs(amount) > 0,
            entry_price=_required_float(row.get("entryPrice"), "entryPrice"),
            break_even_price=_optional_float(row.get("breakEvenPrice")) or 0.0,
            mark_price=_required_float(row.get("markPrice"), "markPrice"),
            unrealized_profit=_required_float(row.get("unRealizedProfit"), "unRealizedProfit"),
            liquidation_price=_required_float(row.get("liquidationPrice"), "liquidationPrice"),
            isolated_margin=_optional_float(row.get("isolatedMargin")) or 0.0,
            notional=_optional_float(row.get("notional")) or 0.0,
            margin_asset=row.get("marginAsset"),
            isolated_wallet=_optional_float(row.get("isolatedWallet")) or 0.0,
            initial_margin=_optional_float(row.get("initialMargin")) or 0.0,
            maintenance_margin=_optional_float(row.get("maintMargin")) or 0.0,
            position_initial_margin=_optional_float(row.get("positionInitialMargin")) or 0.0,
            open_order_initial_margin=_optional_float(row.get("openOrderInitialMargin")) or 0.0,
            adl=_optional_int(row.get("adl")),
            update_time=_optional_int(row.get("updateTime")),
            raw_response_included=False,
        )

    def _authenticated_get(self, path: str, parameters: dict[str, Any], server_time: int | None = None) -> tuple[BinanceReadOnlyHTTPResponse, BinanceFuturesTestnetAuthenticatedRequestMetadata]:
        self._require_allowed_method("GET")
        self._require_allowed_auth_path(path)
        self._require_credentials()
        timestamp = int(server_time if server_time is not None else self._now_ms())
        recv_window = int(self.config.recv_window_ms)
        if recv_window <= 0 or recv_window > int(self.config.maximum_recv_window_ms):
            raise ValueError("recvWindow is invalid")
        query_parameters = {"timestamp": timestamp, "recvWindow": recv_window, **parameters}
        canonical = self._canonical_query(query_parameters)
        signature = self._signature(canonical)
        request_parameters = {**query_parameters, "signature": signature}
        url = f"{self.config.rest_base_url}{path}?{self._canonical_query(request_parameters)}"
        headers = {"X-MBX-APIKEY": self.env[self.config.api_key_env_var]}
        metadata = BinanceFuturesTestnetAuthenticatedRequestMetadata(
            method="GET",
            host=self.ALLOWED_HOST,
            path=path,
            parameter_names=sorted(query_parameters.keys()),
            timestamp=timestamp,
            recv_window_ms=recv_window,
            signature_generated=True,
            signature_redacted=True,
            api_key_header_used=True,
            request_transmitted=False,
            raw_url_exposed=False,
            raw_headers_exposed=False,
            raw_response_included=False,
        )
        last_error: Exception | None = None
        for attempt in range(int(self.config.max_authenticated_fetch_retries) + 1):
            try:
                response = self.authenticated_get(url, int(self.config.request_timeout_seconds), headers)
                final_host = urlparse(response.final_url).hostname
                if final_host != self.ALLOWED_HOST:
                    raise ValueError("final response host is not allowlisted")
                metadata.request_transmitted = True
                metadata.response_received = True
                metadata.response_status_code = int(response.status_code)
                metadata.final_host_validated = True
                metadata.response_bytes = response.response_bytes
                metadata.retry_count = attempt
                return response, metadata
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"authenticated read-only request failed safely: {_sanitize_error(last_error)}")

    def _public_get(self, path: str) -> BinanceReadOnlyHTTPResponse:
        if path != self.config.server_time_path:
            raise ValueError("public path is not allowed")
        url = f"{self.config.rest_base_url}{path}"
        response = self.http_get(url, int(self.config.request_timeout_seconds))
        final_host = urlparse(response.final_url).hostname
        if final_host != self.ALLOWED_HOST:
            raise ValueError("final response host is not allowlisted")
        return response

    def _default_public_get(self, url: str, timeout: int) -> BinanceReadOnlyHTTPResponse:
        request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-ReadOnly"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact public testnet allowlist is validated.
            body = response.read()
            payload = json.loads(body.decode("utf-8")) if body else {}
            return BinanceReadOnlyHTTPResponse(int(response.status), response.geturl(), payload, len(body))

    def _default_authenticated_get(self, url: str, timeout: int, headers: dict[str, str]) -> BinanceReadOnlyHTTPResponse:
        request = Request(url, method="GET", headers={"User-Agent": "ICT-Pro-Trading-Bot-Testnet-ReadOnly", **headers})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - exact authenticated testnet allowlist is validated.
            body = response.read()
            payload = json.loads(body.decode("utf-8")) if body else {}
            return BinanceReadOnlyHTTPResponse(int(response.status), response.geturl(), payload, len(body))

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

    def _require_allowed_method(self, method: str) -> None:
        if method != "GET" or self.config.allowed_http_methods != ["GET"]:
            raise ValueError("Only GET authenticated read-only transport is allowed")

    def _require_allowed_auth_path(self, path: str) -> None:
        blocked_parts = ("order", "leverage", "margin", "positionSide", "multiAssetsMargin", "listenKey", "income", "trade")
        if path not in self.ALLOWED_AUTH_PATHS or path not in self.config.allowed_authenticated_paths or any(part in path for part in blocked_parts):
            raise ValueError("authenticated path is not allowed")

    def _require_credentials(self) -> None:
        metadata = self.inspect_credential_presence()
        if not metadata.credentials_complete:
            raise ValueError("dedicated testnet credentials are incomplete")

    def _signature(self, canonical_query: str) -> str:
        secret = self.env.get(self.config.api_secret_env_var)
        if not secret:
            raise ValueError("dedicated testnet API secret is missing")
        return hmac.new(secret.encode("utf-8"), canonical_query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _canonical_query(self, parameters: dict[str, Any]) -> str:
        return urlencode(sorted((key, value) for key, value in parameters.items() if value is not None))

    def _now_ms(self) -> int:
        if self.now_ms_provider is not None:
            return int(self.now_ms_provider())
        return int(time.time() * 1000)

    def submit_order(self, *args, **kwargs):
        return self._blocked("submit_order")

    def test_submit_order(self, *args, **kwargs):
        return self._blocked("test_submit_order")

    def cancel_order(self, *args, **kwargs):
        return self._blocked("cancel_order")

    def modify_order(self, *args, **kwargs):
        return self._blocked("modify_order")

    def fetch_open_orders(self, *args, **kwargs):
        return self._blocked("fetch_open_orders")

    def fetch_all_orders(self, *args, **kwargs):
        return self._blocked("fetch_all_orders")

    def fetch_trades(self, *args, **kwargs):
        return self._blocked("fetch_trades")

    def fetch_income(self, *args, **kwargs):
        return self._blocked("fetch_income")

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

    def create_listen_key(self, *args, **kwargs):
        return self._blocked("create_listen_key")

    def open_user_stream(self, *args, **kwargs):
        return self._blocked("open_user_stream")

    def open_websocket(self, *args, **kwargs):
        return self._blocked("open_websocket")

    def _blocked(self, operation: str):
        raise BinanceFuturesTestnetReadOnlyOperationBlocked(f"{self.BLOCKED_DECISION}: {operation}")


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _required_float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not numeric") from exc


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _sanitize_error(exc: Exception | None) -> str:
    if exc is None:
        return "unknown error"
    text = str(exc)
    for marker in ("signature=", "X-MBX-APIKEY", "apiKey"):
        if marker in text:
            return "redacted authenticated transport error"
    return text[:180]
