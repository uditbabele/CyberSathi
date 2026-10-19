# Production-readiness checklist

This repository adds foundational controls, but passing this checklist requires deployment-specific work and independent review.

## Authentication and secrets
- [ ] Change demo admin password and JWT secret; inject secrets from a secret manager.
- [ ] Serve only behind HTTPS; configure trusted proxy and secure transport.
- [ ] Add rate limiting, login throttling, account lockout/recovery, token revocation/rotation, and MFA for administrators.
- [ ] Add CSRF protections if switching to cookie-based sessions; restrict CORS to known origins.
- [ ] Create least-privilege DB credentials; rotate credentials and keys.

## Data and operational controls
- [ ] Run PostgreSQL in a private network; encrypt backups and disks.
- [ ] Define retention, deletion, access, and privacy rules for financial/complaint records.
- [ ] Restrict exports and uploads by role; scan uploads and add content/row-count limits.
- [ ] Add pagination and asynchronous jobs for large graph analyses.
- [ ] Add observability, alerting, backup restore drills, disaster recovery, and incident response.
- [ ] Send audit logs to append-only/tamper-resistant storage; restrict audit access.
- [ ] Review and test file import transactions for rollback/atomicity.

## Database migrations
- [ ] Use Alembic migrations in staging before production.
- [ ] Take and verify a backup before every schema migration.
- [ ] Review generated migration SQL, test upgrade and downgrade paths, and rehearse rollback.
- [ ] Do not rely on `create_all` for production schema evolution.

## Model validation and governance
- [ ] Obtain lawful, representative, quality-checked labelled data.
- [ ] Define label quality, leakage controls, train/validation/test splits by time and entity.
- [ ] Report precision, recall, PR-AUC, calibration, false-positive rate, and confidence intervals.
- [ ] Evaluate by relevant subgroups and investigate disparate error rates.
- [ ] Run out-of-time and drift testing; define thresholds and human review process.
- [ ] Have a qualified independent reviewer reproduce results before operational claims.
- [ ] Keep synthetic evaluation results separate from real-world performance claims.

## Security testing
- [ ] Run dependency vulnerability scanning and software composition analysis.
- [ ] Run static analysis, secret scanning, and dynamic testing.
- [ ] Commission independent penetration testing before processing sensitive data.
- [ ] Test authorization boundaries, malicious CSV input, oversized payloads, brute force, and audit tampering.
- [ ] Establish vulnerability response and patching procedures.

## Current limitations to disclose
- Password hashing/JWT implementation is a prototype baseline, not a substitute for a vetted identity provider.
- The audit table is not tamper-proof by itself.
- Hashing a record does not prove the original source was authentic.
- The model and text matching outputs are review candidates, not evidence of guilt.
- Do not process real sensitive financial data until controls have been reviewed and approved.
