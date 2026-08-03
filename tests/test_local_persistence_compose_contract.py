from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.persistence.yml"
RUNBOOK_PATH = ROOT / "docs" / "validation_gate_runbook.md"


def _compose_text() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def test_compose_declares_exact_postgres_service_contract() -> None:
    text = _compose_text()

    assert re.search(r"^services:\n  ict_pro_postgres:", text, re.MULTILINE)
    assert "container_name: ict_pro_tradingbot_postgres" in text
    assert "image: postgres:16-alpine" in text
    assert "restart: unless-stopped" in text


def test_compose_exposes_postgres_on_localhost_default_port_only() -> None:
    text = _compose_text()

    assert '"127.0.0.1:${ICT_POSTGRES_PORT:-55432}:5432"' in text
    assert "0.0.0.0" not in text
    assert re.search(r"\$\{ICT_POSTGRES_PORT:-55432\}:5432", text)


def test_compose_uses_only_required_postgres_environment_references_without_defaults() -> None:
    text = _compose_text()

    assert "POSTGRES_DB: ${ICT_POSTGRES_DB}" in text
    assert "POSTGRES_USER: ${ICT_POSTGRES_USER}" in text
    assert "POSTGRES_PASSWORD: ${ICT_POSTGRES_PASSWORD}" in text
    assert "${ICT_POSTGRES_DB:-" not in text
    assert "${ICT_POSTGRES_USER:-" not in text
    assert "${ICT_POSTGRES_PASSWORD:-" not in text
    assert "DATABASE_URL" not in text
    assert "ICT_DATABASE_URL" not in text


def test_compose_uses_exact_named_volume_and_postgres_data_mount() -> None:
    text = _compose_text()

    assert "- ict_pro_tradingbot_postgres_data:/var/lib/postgresql/data" in text
    assert re.search(r"^volumes:\n  ict_pro_tradingbot_postgres_data:", text, re.MULTILINE)
    assert "/var/run/docker.sock" not in text


def test_compose_healthcheck_uses_pg_isready_with_configured_database_and_user() -> None:
    text = _compose_text()

    assert "pg_isready" in text
    assert 'pg_isready -d "$${POSTGRES_DB}" -U "$${POSTGRES_USER}"' in text
    assert re.search(r"^\s+interval:\s+\S+", text, re.MULTILINE)
    assert re.search(r"^\s+timeout:\s+\S+", text, re.MULTILINE)
    assert re.search(r"^\s+retries:\s+\S+", text, re.MULTILINE)
    assert re.search(r"^\s+start_period:\s+\S+", text, re.MULTILINE)


def test_compose_does_not_define_application_or_dangerous_docker_features() -> None:
    text = _compose_text()

    assert re.search(r"^  ict_pro_postgres:", text, re.MULTILINE)
    assert not re.search(r"^  (backend|app|application|api|smc_backend):", text, re.MULTILINE)
    assert "BINANCE" not in text
    assert "network_mode: host" not in text
    assert "privileged: true" not in text
    assert "docker.sock" not in text
    assert "POSTGRES_PASSWORD:" in text
    assert "secret" not in text.lower()
    assert "changeme" not in text.lower()
    assert "password123" not in text.lower()


def test_runbook_contains_local_persistence_contract_commands_and_boundaries() -> None:
    text = _runbook_text()

    assert "### Local Persistence Provisioning Contract" in text
    assert "supervised local/Testnet persistence only" in text
    assert "does not authorize C2C, credentials, permit issue, signing, or Binance contact" in text
    assert "ICT_POSTGRES_DB, ICT_POSTGRES_USER, and ICT_POSTGRES_PASSWORD" in text
    assert "outside the repository" in text
    assert "must not be committed, printed, pasted into Codex prompts, or included in screenshots" in text
    assert "docker compose -f docker-compose.persistence.yml config" in text
    assert "docker compose -p ict-pro-tradingbot -f docker-compose.persistence.yml up -d" in text
    assert "docker compose -p ict-pro-tradingbot -f docker-compose.persistence.yml ps" in text
    assert "docker compose -p ict-pro-tradingbot -f docker-compose.persistence.yml down" in text
    assert "`down -v` is prohibited unless separately authorized" in text
    assert "Migration and durable state initialization remain separate future passes" in text
    assert "Container health does not prove schema readiness or kill-switch state" in text
    assert "old-project containers must not be reused" in text
    assert "DATABASE_URL=" not in text
    assert "ICT_DATABASE_URL=" not in text
