from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from infrastructure.persistence.live_execution_permit_persistence import LiveExecutionPermitPersistence, LiveExecutionPermitPersistenceError


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
        "revoked_at": None if permit.revoked_at is None else permit.revoked_at.isoformat(),
        "version": permit.version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revoke an issued one-time live execution permit.")
    parser.add_argument("--permit-id", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args(argv)
    persistence = LiveExecutionPermitPersistence()
    try:
        persistence.ensure_available()
        permit = persistence.revoke(args.permit_id, expected_version=args.expected_version, reason_code=args.reason_code, confirmation=args.confirmation)
        print(json.dumps(_permit_json(permit), sort_keys=True))
        return 0
    except LiveExecutionPermitPersistenceError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        return 1
    finally:
        persistence.close()


if __name__ == "__main__":
    raise SystemExit(main())
