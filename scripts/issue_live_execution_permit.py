from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from infrastructure.persistence.live_execution_permit_persistence import LiveExecutionPermitPersistence, LiveExecutionPermitPersistenceError
from infrastructure.security.live_execution_request_fingerprint import RequestFingerprintError, build_live_execution_request_fingerprint


def _permit_json(permit) -> dict:
    return {
        "permit_id": permit.permit_id,
        "operation": permit.operation.value,
        "environment": permit.environment,
        "symbol": permit.symbol,
        "subject_type": permit.subject_type,
        "subject_id": permit.subject_id,
        "request_fingerprint": permit.request_fingerprint,
        "state": permit.state.value,
        "issued_at": permit.issued_at.isoformat(),
        "expires_at": permit.expires_at.isoformat(),
        "version": permit.version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue a one-time TESTNET BTCUSDT live execution permit.")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=300)
    parser.add_argument("--issued-by", required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args(argv)
    persistence = LiveExecutionPermitPersistence()
    try:
        payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("operation") != args.operation:
            raise RequestFingerprintError()
        fingerprint = build_live_execution_request_fingerprint(payload)
        persistence.ensure_available()
        permit = persistence.issue(fingerprint, ttl_seconds=args.ttl_seconds, issued_by=args.issued_by, confirmation=args.confirmation)
        print(json.dumps(_permit_json(permit), sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, RequestFingerprintError):
        print(json.dumps({"error": "PERMIT_INVALID"}), file=sys.stderr)
        return 1
    except LiveExecutionPermitPersistenceError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        return 1
    finally:
        persistence.close()


if __name__ == "__main__":
    raise SystemExit(main())
