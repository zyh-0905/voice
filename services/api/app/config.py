"""Runtime configuration helpers."""
import os

DEMO_DEDUPE_HMAC_SECRET = "voicelens-demo-dedupe-secret"

def dedupe_hmac_secret() -> tuple[str, bool]:
    """Return HMAC secret and whether the explicit demo fallback was used."""
    value = os.getenv("DEDUPE_HMAC_SECRET")
    if value:
        return value, False
    # Keep local/demo fixtures runnable while making the fallback observable.
    return DEMO_DEDUPE_HMAC_SECRET, True

