from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from infrastructure.persistence.live_execution_permit_persistence import LiveExecutionPermitPersistence, LiveExecutionPermitPersistenceError


def _permit_json(permit, effective_expired: bool) -> dict:
    return {
        "permit_id": permit.permit_id,
        "operation": permit.operation.value,
        "environment": permit.environment,
        "symbol": permit.symbol,
        "subject_type": permit.subject_type,
        "subject_id": permit.subject_id,
        "request_fingerprint": permit.request_fingerprint,
        "state": permit.state.value,
        "effective_expired": effective_expired,
        "issued_at": permit.issued_at.isoformat(),
        "expires_at": permit.expires_at.isoformat(),
        "consumed_at": None if permit.consumed_at is None else permit.consumed_at.isoformat(),
        "revoked_at": None if permit.revoked_at is None else permit.revoked_at.isoformat(),
        "expired_at": None if permit.expired_at is None else permit.expired_at.isoformat(),
        "version": permit.version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show a one-time live execution permit without mutating it.")
    parser.add_argument("--permit-id", required=True)
    args = parser.parse_args(argv)
    persistence = LiveExecutionPermitPersistence()
    try:
        persistence.ensure_available()
        permit, effective_expired = persistence.show(args.permit_id)
        if permit is None:
            print(json.dumps({"error": "PERMIT_NOT_FOUND"}), file=sys.stderr)
            return 1
        print(json.dumps(_permit_json(permit, effective_expired), sort_keys=True))
        return 0
    except LiveExecutionPermitPersistenceError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        return 1
    finally:
        persistence.close()


if __name__ == "__main__":
    raise SystemExit(main())
