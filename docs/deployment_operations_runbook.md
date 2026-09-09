# Deployment Operations Runbook

## Purpose

This runbook is static procedural documentation only. It does not authorize Codex, tests, scripts, operators, services, schedulers, dashboards, or automation to execute deployment, service mutation, database mutation, backup, restore, rollback, migration, exchange transport, live execution, live orders, permit changes, or dashboard integration.

All deployment and operations decisions fail closed. Missing, malformed, ambiguous, stale, contradictory, unavailable, or unsanitizable evidence is blocking evidence.

## Deployment Boundary

Deployment activity requires a separate explicit authority checkpoint and a human operator decision. This runbook defines repository-local policy only; it does not deploy anything and must not be used as execution approval.

The deployment boundary preserves these defaults:

- production trading remains disabled;
- Binance Futures Testnet/Demo is the only exchange environment ever considered when separately authorized;
- BTCUSDT is the only approved trading scope;
- automated tests must not use credentials;
- automated tests must not contact exchanges;
- no service start, stop, restart, or replacement is authorized by this document.

## Environment Separation Policy

Environments must remain separated by purpose, configuration, operator authorization, and evidence. Local development, automated tests, supervised Testnet/Demo operations, and any future production-readiness review are distinct states.

Non-secret configuration may define environment names, expected roles, and fail-closed defaults. Secret values must remain outside the repository and outside automated tests. Unknown, missing, or contradictory environment evidence blocks promotion and deployment preparation.

If exchange interaction is ever separately authorized, it remains Binance Futures Testnet/Demo only, BTCUSDT only, production disabled, and explicitly supervised. No real exchange transport is allowed from this Phase I runbook.

## Secret Management Policy

Secret management is policy-only in this pass. This runbook must not contain real secret values, usable credential examples, signatures, authenticated URLs, authorization headers, token material, database authentication material, or connection strings containing sensitive values.

Secret categories include exchange credentials, database authentication material, signing material, API access material, operator authentication material, and external service access material. Values for these categories must be provisioned outside automated tests and outside Codex prompts by a human operator under a separately approved procedure.

Secret handling rules:

- do not commit secret values;
- do not log secret values;
- do not paste secret values into prompts, reports, runbooks, screenshots, or test fixtures;
- do not validate live credentials in automated tests;
- do not compare, hash, print, serialize, or inspect secret values;
- fail closed when required secret handling evidence is unavailable or ambiguous.

## Backup Procedure Policy

Backup execution is not authorized by this runbook. A future backup procedure requires separate operator authorization, a defined target environment, a defined non-secret evidence record, and confirmation that backup activity will not mutate trading, exchange, permit, dashboard, or runtime service state.

Before any separately authorized backup action, the operator must record sanitized evidence of repository branch, HEAD, environment, database or artifact scope, retention expectation, and safety boundary. If the operator cannot prove scope, target, retention, or sanitization, the required decision is `STOP - BACKUP BLOCKED`.

Verification expectations are policy-only: a backup artifact must be attributable, restorable under a separately authorized restore procedure, and free of logged secret values. This document does not provide or authorize backup commands.

## Restore Procedure Policy

Restore execution is not authorized by this runbook. A future restore procedure requires separate operator authorization, a defined restore source, a defined target environment, a pre-restore evidence package, and explicit confirmation that restore will not bypass safety gates.

Restore preparation must prove that production trading remains disabled, live orders remain prohibited, permit state is not manually rewritten, and exchange state is not inferred from restored local data. If source integrity, target scope, compatibility, or safety impact cannot be proven, the required decision is `STOP - RESTORE BLOCKED`.

This document does not provide or authorize restore commands.

## Rollback Procedure Policy

Rollback execution is not authorized by this runbook. A future rollback requires separate operator authorization, an exact rollback target, evidence of current state, evidence of the last accepted state, and a fail-closed operator decision.

Rollback must not discard unreviewed user work, rewrite Git history, change permit state, issue or consume permits, mutate exchange state, or hide unresolved recovery evidence. If the rollback path requires Git mutation, service mutation, migration execution, database mutation, backup execution, or restore execution, it must be covered by a separate explicit authority checkpoint.

This document does not provide or authorize rollback commands.

## Process Supervision Policy

Process supervision policy is operator-visible status and escalation only. This runbook does not start, stop, restart, reload, replace, schedule, or supervise services.

Expected operator-visible checks include service health, runtime status, kill-switch status, recovery-required status, persistence status, readiness status, validation status, safety warnings, and operational metrics when available from existing repository-local surfaces.

Controlled startup and shutdown expectations must be documented in a future separately authorized procedure before any service mutation occurs. If health state is unavailable, stale, malformed, contradictory, or unsanitizable, the required decision is `STOP - SERVICE MUTATION BLOCKED`.

## Health / Status Surfaces

Existing backend-authoritative status surfaces should be used only when separately authorized for read-only status collection. Relevant repository-local surfaces include:

- operator status;
- kill-switch status;
- recovery status;
- readiness status;
- safety status;
- persistence status;
- read-only execution and exchange-order views where already implemented.

These status surfaces do not authorize deployment, exchange transport, mutation, permit changes, or service-control actions. Unavailable or ambiguous health evidence fails closed.

## Monitoring and Alerting References

Monitoring and alerting are evidence layers, not execution authority. Repository-local observability references include structured operational logging, operational metrics, operator warnings, readiness evidence, recovery evidence, persistence status, and the incident-response runbook.

This runbook does not add monitoring code, alert delivery, alert acknowledgement, notification services, external dependencies, schedulers, webhooks, or automated remediation.

## Versioned Configuration Expectations

Non-secret configuration must be version-controlled where appropriate and must include explicit schema or version evidence when the local contract requires it. Secrets must not be committed.

Configuration changes require explicit review. Unknown, missing, malformed, stale, or contradictory required configuration fails closed. Configuration must not be changed by this runbook, and configuration changes must not be used to bypass safety gates.

## Disaster Recovery Procedure Policy

Disaster recovery is policy-only in this pass. A future disaster recovery procedure requires separate authorization, sanitized incident evidence, environment scope, backup/restore compatibility evidence, operator approval, and post-recovery verification expectations.

Disaster recovery must preserve fail-closed behavior. It must not infer exchange state from local state alone, must not retry uncertain POST or DELETE mutations, must not refund or reuse consumed permits, and must not resume operation when recovery evidence is incomplete.

If disaster recovery requires backup execution, restore execution, migration execution, service mutation, database mutation, network access, or exchange interaction, a new explicit authority checkpoint is required before action.

## Operator Access-Control Policy

Operator access control follows least privilege and explicit authorization. Operators must not share credentials, log credentials, automate privilege elevation, bypass safety gates, or use dashboard actions as mutation authorization.

Every sensitive operation requires a named operator, separate approval, a sanitized evidence package, and an exact scope. Frontend state is never authoritative for exchange mutation safety. A signal, alert, button, or CLI phrase is not sufficient authority by itself.

No automated elevation, hidden access expansion, shared credential use, or emergency bypass is authorized by this runbook.

## Stop Conditions

Stop immediately and fail closed when:

- required evidence is missing, malformed, ambiguous, stale, contradictory, unavailable, or unsanitizable;
- secret values would need to be read, printed, compared, hashed, stored, or embedded;
- deployment execution would be required;
- service start, stop, restart, reload, replacement, or mutation would be required;
- Docker, cloud deployment, SSH, or remote shell access would be required;
- migration execution would be required;
- backup execution would be required;
- restore execution would be required;
- rollback execution would be required;
- database mutation or persistence writes would be required;
- Binance or exchange transport would be required;
- live execution or live orders would be required;
- permit issue, consume, revoke, refund, renew, replacement, reuse, or bypass would be required;
- dashboard integration would be required.

The required operator decision for these cases is `STOP - DEPLOYMENT OPERATIONS BLOCKED`.

## Prohibited Actions

This runbook prohibits:

- deployment execution;
- service start, stop, restart, reload, replacement, or mutation;
- Docker or cloud deployment mutation;
- SSH or remote shell;
- migration execution;
- backup execution;
- restore execution;
- rollback execution;
- database mutation;
- persistence writes;
- Binance transport;
- exchange transport;
- exchange clients;
- credential access;
- secret output;
- live execution;
- live orders;
- permit changes;
- permit bypass;
- dashboard integration;
- production enablement;
- automated remediation;
- hidden retries;
- safety-gate overrides.

This runbook is not an operational command list. It is static documentation for future separately authorized deployment and operations procedures.
