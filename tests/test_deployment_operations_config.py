from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs" / "deployment_operations.json"


def _raw_text() -> str:
    return CONFIG.read_text(encoding="utf-8")


def _config() -> dict:
    return json.loads(_raw_text())


def _all_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            strings.extend(_all_strings(key))
            strings.extend(_all_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_all_strings(item))
        return strings
    return []


def test_config_file_exists_and_is_valid_json() -> None:
    assert CONFIG.exists()
    assert isinstance(_config(), dict)


def test_schema_version_exists_and_is_explicit() -> None:
    config = _config()

    assert config["schema_version"] == "1.0"
    assert config["versioned_configuration"]["schema_version_explicit"] is True


def test_allowed_environment_roles_exist_and_unknown_roles_fail_closed() -> None:
    config = _config()
    environments = config["environments"]
    names = {environment["name"] for environment in environments}

    assert names == {
        "local_development",
        "automated_tests",
        "supervised_testnet_demo",
        "production_readiness_review",
    }
    assert all(environment["production_disabled"] is True for environment in environments)
    assert all(environment["automated_tests_may_use_credentials"] is False for environment in environments)
    assert all(environment["exchange_transport_authorized"] is False for environment in environments)
    assert config["unknown_environment_role"] == {
        "authorized": False,
        "readiness_status": "NOT_READY",
        "reason_code": "UNKNOWN_ENVIRONMENT_ROLE_FAIL_CLOSED",
    }


def test_production_disabled_and_no_live_authority_are_encoded() -> None:
    scope = _config()["trading_scope"]

    assert scope["production_disabled"] is True
    assert scope["production_trading_authorized"] is False
    assert scope["live_order_authority"] is False
    assert scope["exchange_transport_authority"] is False


def test_btcusdt_and_testnet_demo_policy_are_encoded() -> None:
    scope = _config()["trading_scope"]

    assert scope["symbol"] == "BTCUSDT"
    assert scope["symbol_scope"] == "BTCUSDT_ONLY"
    assert "Testnet/Demo" in scope["exchange_policy"]
    assert "separately authorized" in scope["exchange_policy"]


def test_expected_environment_variable_names_are_names_only() -> None:
    names = _config()["expected_env_names"]

    assert names == sorted(names)
    assert names == ["ICT_DATABASE_URL", "ICT_RUNTIME_ENV"]
    assert all(name.isupper() for name in names)
    assert all("=" not in name for name in names)
    assert all("://" not in name for name in names)


def test_no_environment_variable_values_are_embedded() -> None:
    text = _raw_text()

    assert "postgresql://" not in text
    assert "sqlite://" not in text
    assert "mysql://" not in text
    assert "DATABASE_URL=" not in text
    assert "ICT_DATABASE_URL=" not in text
    assert "ICT_RUNTIME_ENV=" not in text


def test_secret_categories_contain_categories_only() -> None:
    categories = _config()["secret_categories"]
    names = {category["name"] for category in categories}

    assert names == {
        "database_credentials",
        "exchange_api_credentials",
        "operator_credentials",
        "signing_material",
    }
    assert all(category["values_allowed_in_repository"] is False for category in categories)
    assert all(category["values_allowed_in_automated_tests"] is False for category in categories)
    assert all("value" not in category for category in categories)
    assert all("example" not in category for category in categories)


def test_no_secret_values_or_credential_material_are_embedded() -> None:
    text = _raw_text()
    forbidden_patterns = [
        r"sk-[a-z0-9]",
        r"akia[0-9a-z]{16}",
        r"bearer\s+[0-9a-z._-]+",
        r"authorization:",
        r"signature=",
        r"://[^<\s]*:[^<\s]*@",
        r"password\s*[:=]",
        r"token\s*[:=]",
        r"secret\s*[:=]",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text, flags=re.IGNORECASE) is None


def test_fail_closed_defaults_are_encoded() -> None:
    defaults = _config()["fail_closed_defaults"]

    assert defaults["missing_required_configuration_authorized"] is False
    assert defaults["unknown_required_configuration_authorized"] is False
    assert defaults["malformed_required_configuration_authorized"] is False
    assert defaults["ambiguous_operational_evidence_authorized"] is False
    assert defaults["default_readiness_status"] == "NOT_READY"


def test_prohibited_operational_actions_are_encoded() -> None:
    actions = set(_config()["prohibited_actions"])

    assert {
        "deployment_execution",
        "service_start_stop_restart",
        "service_mutation",
        "credential_access",
        "secret_value_access",
        "secret_output",
        "secret_storage",
        "secret_rotation",
        "binance_transport",
        "exchange_transport",
        "exchange_clients",
        "live_execution",
        "live_orders",
        "permit_changes",
        "persistence_mutation",
        "database_mutation",
        "migration_execution",
        "backup_execution",
        "restore_execution",
        "rollback_execution",
        "docker_cloud_deployment_mutation",
        "ssh",
        "remote_shell",
        "dashboard_integration",
    }.issubset(actions)


def test_health_status_surface_names_are_declared_without_remote_dependencies() -> None:
    surfaces = _config()["health_status_surfaces"]

    assert surfaces == [
        "operator_status",
        "kill_switch_status",
        "recovery_status",
        "readiness_status",
        "safety_status",
        "persistence_status",
    ]
    assert all("http" not in surface for surface in surfaces)
    assert all("/" not in surface for surface in surfaces)


def test_versioned_configuration_expectations_are_encoded() -> None:
    versioned = _config()["versioned_configuration"]

    assert versioned["non_secret_configuration_version_controlled"] is True
    assert versioned["secret_values_excluded_from_version_control"] is True
    assert versioned["missing_required_configuration_fails_closed"] is True
    assert versioned["unknown_required_configuration_fails_closed"] is True
    assert versioned["configuration_changes_require_explicit_review"] is True
    assert versioned["schema_version_explicit"] is True


def test_config_structure_is_deterministic() -> None:
    first = _config()
    second = _config()

    assert first == second
    assert list(first) == [
        "schema_version",
        "environments",
        "unknown_environment_role",
        "trading_scope",
        "expected_env_names",
        "secret_categories",
        "fail_closed_defaults",
        "prohibited_actions",
        "health_status_surfaces",
        "versioned_configuration",
    ]


def test_no_python_production_contract_is_required() -> None:
    config = _config()
    strings = "\n".join(_all_strings(config)).casefold()

    assert "production_code_required" not in config
    assert "python production" not in strings
    assert config["versioned_configuration"]["schema_version_explicit"] is True
