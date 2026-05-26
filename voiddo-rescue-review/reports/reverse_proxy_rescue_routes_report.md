# Rescue Reverse Proxy Routes Report

Updated: 2026-05-26 IDT

## DNS

All required Rescue subdomains resolve to `69.62.122.223`:

- `rescue.voiddo.com`
- `app.rescue.voiddo.com`
- `api.rescue.voiddo.com`
- `audit.rescue.voiddo.com`
- `go.rescue.voiddo.com`
- `status.rescue.voiddo.com`

## Implemented Routes

Dedicated Rescue-only nginx configs are active:

- `/etc/nginx/sites-available/rescue.voiddo.com`
- `/etc/nginx/sites-available/rescue-subdomains.voiddo.com`

The Rescue compose stack now binds only localhost ports:

- web: `127.0.0.1:18081 -> 3000`
- api: `127.0.0.1:18082 -> 8080`

No Rescue app/API port is exposed directly to the public internet.

## TLS

Issued Let’s Encrypt certificate:

- Certificate name: `rescue-subdomains.voiddo.com`
- SANs:
  - `app.rescue.voiddo.com`
  - `api.rescue.voiddo.com`
  - `audit.rescue.voiddo.com`
  - `go.rescue.voiddo.com`
  - `status.rescue.voiddo.com`
- Expires: 2026-08-24

## Public Curl Results

- `https://rescue.voiddo.com/`: `200`
- `https://app.rescue.voiddo.com/admin`: `401` expected, admin auth gate active
- `https://api.rescue.voiddo.com/health`: `200`
- `https://audit.rescue.voiddo.com/r/demo`: `200`
- `https://go.rescue.voiddo.com/unsubscribe/test`: `200`
- `https://status.rescue.voiddo.com/`: `200`

## Download Compatibility

The main Rescue root now serves the product landing, but artifact links remain live:

- `https://rescue.voiddo.com/downloads/voiddo-rescue-mvp-code-2026-05-26.zip`
- `https://rescue.voiddo.com/voiddo-rescue-mvp-code-2026-05-26.zip`

## Decision

`PASS`

Nested Rescue public routes are now wired without changing non-Rescue vhosts.
