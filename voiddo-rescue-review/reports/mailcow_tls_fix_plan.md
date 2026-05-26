# Mailcow TLS Fix Plan

Updated: 2026-05-26 12:05 IDT

## Goal

Make strict TLS verification pass for Rescue SMTP/IMAP without disrupting the existing `voiddo.com` mail flow.

Rescue runtime will continue to use:

- `SMTP_HOST=mail.voiddo.com`
- `IMAP_HOST=mail.voiddo.com`
- Rescue sender identities such as `audit@voiddorescue.com`

This avoids requiring a new SAN for `mail.voiddorescue.com` during this pass.

## Pre-Change State

Mailcow config safe keys:

- `MAILCOW_HOSTNAME=mail.voiddo.com`
- `SKIP_LETS_ENCRYPT=y`
- `ADDITIONAL_SAN=`
- `ENABLE_SSL_SNI=n`

Mailcow currently serves a self-signed certificate on SMTP/IMAP:

- Subject/CN: `mail.voiddo.com`
- Issuer: same self-signed Mailcow certificate
- SMTP/IMAP strict TLS verification: FAIL

The host already has a trusted Let’s Encrypt certificate:

- Path: `/etc/letsencrypt/live/mail.voiddo.com/fullchain.pem`
- Key: `/etc/letsencrypt/live/mail.voiddo.com/privkey.pem`
- Subject/SAN: `mail.voiddo.com`
- Issuer: Let’s Encrypt E7
- Expiry: 2026-07-18

## Backup

Backup created before certificate mutation:

- `/opt/voiddo-rescue/backups/mailcow-tls-20260526-114401/mailcow.conf`
- `/opt/voiddo-rescue/backups/mailcow-tls-20260526-114401/ssl/`
- `/opt/voiddo-rescue/backups/mailcow-tls-20260526-114401/docker-ps.txt`
- `/opt/voiddo-rescue/backups/mailcow-tls-20260526-114401/mailcow-compose-ps.txt`

The backup directory is mode `700`.

## Documented Procedure Basis

Mailcow documentation for using a custom/non-mailcow ACME certificate says to copy the combined certificate to:

- `data/assets/ssl/cert.pem`
- `data/assets/ssl/key.pem`

It also says not to symlink those files, then restart affected containers: Postfix, Dovecot, and Nginx.

## Chosen Fix

Use the existing host-managed Let’s Encrypt certificate for `mail.voiddo.com` as a custom Mailcow certificate:

1. Copy `/etc/letsencrypt/live/mail.voiddo.com/fullchain.pem` to `/opt/mailcow-dockerized/data/assets/ssl/cert.pem`.
2. Copy `/etc/letsencrypt/live/mail.voiddo.com/privkey.pem` to `/opt/mailcow-dockerized/data/assets/ssl/key.pem`.
3. Preserve plain files, no symlinks.
4. Restart only the affected Mailcow certificate consumers:
   - `postfix-mailcow`
   - `dovecot-mailcow`
   - `nginx-mailcow`

No database, mailbox, domain, queue, or mail flow configuration is changed.

## Rollback

If strict TLS or mail service health fails:

1. Copy backup `ssl/cert.pem` and `ssl/key.pem` back to `/opt/mailcow-dockerized/data/assets/ssl/`.
2. Restart `postfix-mailcow`, `dovecot-mailcow`, and `nginx-mailcow`.
3. Re-run SMTP/IMAP openssl checks and Rescue mail QA.

## Post-Change Checks

- SMTP STARTTLS certificate subject/issuer.
- IMAP TLS certificate subject/issuer.
- Rescue `smtp_agent`.
- Rescue `imap_agent`.
- DNS auth agent.
- Login check for Rescue `audit@voiddorescue.com`.
- Existing Mailcow service status snapshot.

## Applied Result

The chosen fix was applied.

- SMTP STARTTLS now serves Let’s Encrypt certificate for `mail.voiddo.com`.
- IMAP TLS now serves Let’s Encrypt certificate for `mail.voiddo.com`.
- OpenSSL verify return code: `0 (ok)`.
- Rescue `smtp_agent`: PASS.
- Rescue `imap_agent`: PASS.
- All MVP `voiddorescue.com` mailboxes: strict IMAP login PASS.
- Existing `em@voiddo.com`: strict SMTP/IMAP login PASS.
- Mailcow `postfix-mailcow`, `dovecot-mailcow`, and `nginx-mailcow` are running after restart.

Remaining mail launch blocker is not TLS. It is the missing approved deliverability test inbox pool.
