# SDD ledger — plan: docs/superpowers/plans/2026-09-09-voicelens-web-mvp.md
Added expiring bearer tokens with configurable AUTH_TOKEN_TTL_SECONDS, expiry metadata, and token_expired 401 handling.
Verification: backend pytest 22 passed; compileall PASS; frontend typecheck/unit/build PASS; Playwright + axe 4 passed; compose validation PASS.
Remaining: production identity/token persistence and Docker multi-service integration.
