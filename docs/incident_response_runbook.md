# Incident-Response Operator Runbook

## Purpose

This runbook maps existing Phase F operational evidence to safe human incident-response procedures. It is documentation only. It does not create scheduler behavior, alert delivery, alert persistence, acknowledgement workflow, reset workflow, automation, permit authority, signing authority, transport authority, or order authority.

Incident response uses the current evidence layer:

- `GET /api/v1/live/operator/status`
- `GET /api/v1/live/kill-switch/status`
- `GET /api/v1/live/recovery/status`
- `GET /api/v1/live/readiness`
- `GET /api/v1/live/safety/status`
- `GET /api/v1/live/persistence/status`
- read-only persistence views for execution intents and exchange orders
- structured logs emitted by the observability logger
- operational metrics exposed through the operator status snapshot

Every incident decision is fail closed. Unavailable, malformed, ambiguous, missing, contradictory, stale, or unsanitizable evidence is not safe evidence.

## Safety Boundary

Incident-response tooling and procedures must never:

- create execution authority;
- issue, consume, refund, renew, replace, or reuse a permit;
- submit, cancel, modify, or retry an order;
- bypass safety gates;
- alter signing;
- alter transport;
- alter persistence ordering;
- alter reconciliation;
- alter recovery semantics;
- alter kill-switch semantics.

The runbook can guide a human operator to existing backend-authoritative controls only when those controls are separately authorized by their own procedure. It does not make those controls automatic.

## Evidence Collection

For every suspected incident, preserve a sanitized operator record before taking any action:

```text
incident_id: <UNIQUE_INCIDENT_ID>
utc_timestamp: <UTC_TIMESTAMP>
local_date: <LOCAL_DATE>
operator: <OPERATOR>
repository_branch: <BRANCH>
repository_head: <HEAD_SHA>
primary_alert_id: <ALERT_ID_OR_NONE>
primary_status: <STATUS_SUMMARY>
operator_status_updated_at: <UPDATED_AT_OR_UNAVAILABLE>
kill_switch_state: <ENGAGED_RELEASED_OR_UNAVAILABLE>
recovery_required: <TRUE_FALSE_OR_UNAVAILABLE>
persistence_status: <SUMMARY_OR_UNAVAILABLE>
readiness_status: <SUMMARY_OR_UNAVAILABLE>
validation_gate_status: <SUMMARY_OR_UNAVAILABLE>
safety_denials_total: <COUNT_OR_UNAVAILABLE>
active_lock_present: <TRUE_FALSE_OR_UNAVAILABLE>
operator_decision: <STOP_ESCALATE_MONITOR_OR_SEPARATELY_AUTHORIZED_CONTROL>
```

Do not record API keys, API secrets, signatures, authenticated headers, signed URLs, raw authenticated payloads, credential lengths, sensitive SQL, tracebacks, exception chains, raw exchange responses, or internal metadata that cannot be safely shared.

## Incident Categories

### Safety Denial Active

Evidence:

- operator alert `SAFETY_DENIAL_ACTIVE`;
- non-zero `ict_tradingbot_safety_denials_total`;
- structured log entries for safety-denial events when available.

Operator response:

1. Stop any affected operator workflow.
2. Preserve the sanitized operator status, alert, metric, and log evidence.
3. Treat the state as blocking until the denied prerequisite is understood.
4. Do not issue a new permit to work around the denial.
5. Do not retry an authenticated mutation.

### Recovery Required

Evidence:

- operator alert `RECOVERY_REQUIRED`;
- `GET /api/v1/live/recovery/status` reports `required == true`;
- recovery-related warning or structured log evidence;
- persisted mutation identity or protective pair state that indicates post-consume uncertainty.

Operator response:

1. Stop mutation preparation and mutation attempts.
2. Preserve the exact pair, correlation, permit, and persisted mutation identity evidence if available.
3. Do not retry POST or DELETE.
4. Do not refund, renew, replace, or reuse the consumed permit.
5. Use only the existing exact read-only reconciliation or separately authorized supervised recovery path.

`POST /api/v1/live/recovery/run` is a recovery action, not a status check. It must not run automatically and must not run from this incident-response runbook alone.

### Persistence Configuration, Availability, or Schema Issue

Evidence:

- operator alerts `PERSISTENCE_UNCONFIGURED`, `PERSISTENCE_UNAVAILABLE`, or `PERSISTENCE_SCHEMA_NOT_READY`;
- `GET /api/v1/live/persistence/status` reports not configured, unavailable, or schema not ready;
- structured logs for persistence status failures when available.

Operator response:

1. Stop workflows that depend on durable state.
2. Preserve sanitized status and log evidence.
3. Treat persistence uncertainty as blocking for mutation authority.
4. Do not create replacement local state by hand.
5. Do not bypass persistence ordering or recovery checks.

### Kill-Switch State

Evidence:

- operator alert `KILL_SWITCH_ENGAGED`;
- operator alert `KILL_SWITCH_UNAVAILABLE`;
- `GET /api/v1/live/kill-switch/status` reports `ENGAGED`, unavailable, malformed, or ambiguous state.

Operator response:

1. If the kill switch is `ENGAGED`, treat the system as intentionally blocked.
2. If the kill-switch status is unavailable or ambiguous, fail closed.
3. Preserve the durable kill-switch state, version, and timestamp when available.
4. Do not automatically release the kill switch.
5. Do not interpret missing, unavailable, or untrusted kill-switch evidence as safe.

`POST /api/v1/live/kill-switch/engage` and `POST /api/v1/live/kill-switch/release` remain existing backend controls. This runbook does not authorize automatic engagement or release, and release must remain subject to existing safety checks.

### Readiness Failure

Evidence:

- operator alert `READINESS_NOT_READY`;
- `GET /api/v1/live/readiness` reports not ready;
- BTC paper readiness status is unavailable, failed, malformed, ambiguous, or stale.

Operator response:

1. Stop any workflow that depends on readiness.
2. Preserve readiness status, operator status, and related logs.
3. Do not treat partial readiness as execution approval.
4. Do not run BTC readiness, validation gate, or validators unless separately authorized.

### Validation Gate Failure

Evidence:

- operator alert `VALIDATION_GATE_NOT_PASS`;
- operator status reports validation gate state other than pass;
- validation evidence is missing, stale, failed, unavailable, malformed, or ambiguous.

Operator response:

1. Stop promotion or mutation preparation that depends on the gate.
2. Preserve the gate status and operator status evidence.
3. Do not rerun the validation gate from incident response.
4. Do not use incident response as approval to override a failed gate.

### Active Protective or Recovery Lock

Evidence:

- operator alert `ACTIVE_LOCK_PRESENT`;
- operator status reports an active protective or recovery lock;
- lock-related structured log evidence when available.

Operator response:

1. Stop competing operator workflows.
2. Preserve lock-path, lock-owner, timestamp, and sanitized status evidence when available.
3. Do not delete, overwrite, or bypass the lock from incident response.
4. Do not start a second mutation, recovery, or reconciliation path against the same identity.

## Fail-Closed Procedure

Use this procedure whenever any incident category is present or evidence is unavailable, malformed, ambiguous, contradictory, stale, or unsanitizable:

1. Stop the current operator workflow.
2. Do not issue, consume, refund, renew, replace, or reuse a permit.
3. Do not submit, cancel, modify, or retry an order.
4. Collect sanitized evidence from operator status, alerts, metrics, structured logs, readiness, recovery, persistence, and kill-switch status.
5. Record the operator decision as `STOP` unless a separately authorized backend control procedure applies.
6. Escalate to a human maintainer with the sanitized incident record.

Fail-closed status is not recovery-required by itself. Pre-consume denial remains failed safe. Post-consume uncertainty remains recovery-required and must preserve the consumed permit evidence.

## Allowed Operator Actions

Incident response allows these actions:

- read existing status endpoints;
- inspect existing operator alerts and warnings;
- inspect existing operational metrics snapshots;
- inspect existing sanitized structured logs;
- inspect read-only persistence views;
- preserve sanitized evidence;
- stop, defer, or block a workflow;
- escalate to a human maintainer with sanitized evidence;
- follow a separately authorized backend-control procedure when that procedure applies.

Existing backend controls include kill-switch and supervised recovery routes, but this runbook does not authorize running them. They remain governed by their own confirmation, eligibility, and safety checks.

## Prohibited Operator Actions

Incident response prohibits these actions:

- automatic recovery;
- blind POST retry;
- blind DELETE retry;
- permit bypass;
- permit auto-issue;
- permit refund;
- permit renewal;
- permit replacement;
- permit reuse;
- order submission;
- order cancellation;
- order modification;
- signing or authenticated transport;
- manual persistence edits;
- manual lock deletion;
- safety-gate override;
- kill-switch auto-release;
- alert acknowledgement workflow;
- alert reset workflow;
- alert persistence workflow;
- scheduler, notifier, webhook, or automation behavior.

## Human Escalation Boundaries

Escalate to a human maintainer when:

- any blocking or unavailable alert is present;
- status evidence is missing, ambiguous, contradictory, stale, or unsanitizable;
- recovery is required;
- the kill switch is engaged or unavailable;
- persistence is unavailable, unconfigured, or schema-not-ready;
- readiness or validation gate evidence is not passing;
- an active protective or recovery lock exists;
- the operator cannot prove whether an authenticated mutation occurred.

Human escalation may authorize a separate runbook or backend-control procedure. It must not authorize hidden retries, permit reuse, safety bypass, or incident-tool execution authority.

## Standing Rules

No automatic recovery:

- incident response must never invoke recovery automatically;
- recovery status reads do not authorize `POST /api/v1/live/recovery/run`;
- supervised recovery requires its own separate authorization and eligibility checks.

No blind retry:

- POST retry is zero;
- DELETE retry is zero;
- uncertainty uses exact read-only reconciliation or separately authorized recovery only.

No permit reuse or refund:

- consumed permits remain consumed;
- denied or uncertain outcomes do not create automatic replacement permits;
- incident response must not issue, consume, refund, renew, replace, or reuse permits.

No execution authority:

- incident tooling is evidence and human procedure only;
- alerts, metrics, logs, readiness, recovery, persistence, and kill-switch state do not create permission to execute;
- every authenticated mutation remains governed by the existing permit, confirmation, signing, transport, persistence, reconciliation, recovery, and kill-switch contracts.
