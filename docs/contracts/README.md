# Data Contracts

JSON Schema files in this folder document the persisted database record shape for each table.

Each contract describes:

- field names
- field types
- field descriptions
- enum values
- examples

Shared nested JSONB structures, such as `site_filter` and `local_filter`, live in their own schema files and are referenced by table contracts.

Alert persistence is separated into channel-independent `alert_events` and
one-row-per-provider-call `alert_delivery_attempts`.
