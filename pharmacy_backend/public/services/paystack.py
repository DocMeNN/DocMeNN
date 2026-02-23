# public/services/paystack.py
from __future__ import annotations

import hashlib
import hmac
import json
import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

PAYSTACK_BASE = "https://api.paystack.co"


def _paystack_cfg() -> dict:
    """
    Best-effort config resolver.

    Priority:
    1) settings.PAYMENTS["PAYSTACK"] (your intended design)
    2) direct env vars as fallback (PAYSTACK_SECRET_KEY / PAYSTACK_PUBLIC_KEY)
       This prevents "works locally but fails on Render" when PAYMENTS mapping is off.
    """
    payments = getattr(settings, "PAYMENTS", {}) or {}
    cfg = (payments.get("PAYSTACK") or {}) if isinstance(payments, dict) else {}
    if isinstance(cfg, dict):
        return cfg

    # If PAYMENTS exists but not in expected shape, hard-fall back to env
    return {}


def _get_secret_key() -> str:
    cfg = _paystack_cfg()

    sk = (cfg.get("SECRET_KEY") or "").strip()

    # Fallback: read from environment directly (Render uses env vars)
    if not sk:
        sk = (os.environ.get("PAYSTACK_SECRET_KEY") or "").strip()

    if not sk:
        raise RuntimeError(
            "PAYSTACK SECRET_KEY is not configured. "
            "Expected settings.PAYMENTS['PAYSTACK']['SECRET_KEY'] or env PAYSTACK_SECRET_KEY."
        )

    # ---- SAFE DIAGNOSTIC (NO SECRET LEAK) ----
    # Helps us confirm production is using the expected key value.
    # Remove after confirmation.
    try:
        fp = hashlib.sha256(sk.encode("utf-8")).hexdigest()[:12]
        print(f"PAYSTACK_SECRET_KEY_FINGERPRINT={fp} len={len(sk)} prefix={sk[:8]}")
    except Exception:
        # never break payment flow because of diagnostics
        pass

    return sk


def _to_kobo(amount_naira: Decimal) -> int:
    try:
        naira = Decimal(str(amount_naira))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("amount_naira must be a valid Decimal") from exc
    kobo = (naira * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(kobo)


def _safe_preview(text: str, limit: int = 800) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + " …(truncated)"


def _parse_json_or_text(raw: str) -> dict[str, Any]:
    raw = raw or ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {"kind": "json", "json": parsed, "raw": raw}
        return {"kind": "json_non_object", "json": parsed, "raw": raw}
    except Exception:
        return {"kind": "text", "raw": raw}


def _request_json(
    method: str, url: str, *, body: dict | None = None, timeout: int = 25
) -> dict[str, Any]:
    sk = _get_secret_key()
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {sk}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (PaystackClient; +https://example.local) Python-urllib",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method=method,
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed_any = _parse_json_or_text(raw)
    except HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        parsed_any = _parse_json_or_text(raw)

        if parsed_any.get("kind") == "json":
            j = parsed_any.get("json") or {}
            msg = (
                j.get("message")
                or j.get("error")
                or j.get("status")
                or "Paystack rejected request"
            )
            raise RuntimeError(f"Paystack HTTPError: {e.code} {msg}") from e

        preview = _safe_preview(parsed_any.get("raw") or str(e))
        raise RuntimeError(f"Paystack HTTPError: {e.code} {preview}") from e
    except URLError as e:
        raise RuntimeError(f"Paystack URLError: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Paystack request failed: {e}") from e

    if parsed_any.get("kind") != "json":
        raise RuntimeError(
            f"Paystack returned non-JSON: {_safe_preview(parsed_any.get('raw') or '')}"
        )

    return parsed_any.get("json") or {}


def paystack_initialize_transaction(
    *,
    email: str,
    amount_naira: Decimal,
    reference: str,
    callback_url: str = "",
    metadata: dict | None = None,
) -> dict:
    payload: dict = {
        "email": str(email).strip(),
        "amount": _to_kobo(amount_naira),
        "reference": str(reference).strip(),
    }

    if callback_url:
        payload["callback_url"] = str(callback_url).strip()

    if metadata:
        payload["metadata"] = metadata

    parsed = _request_json(
        "POST", f"{PAYSTACK_BASE}/transaction/initialize", body=payload, timeout=25
    )

    if not parsed.get("status"):
        raise RuntimeError(parsed.get("message") or "Paystack init rejected")

    return parsed.get("data") or {}


def verify_paystack_signature(*, raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    sk = _get_secret_key().encode("utf-8")
    computed = hmac.new(sk, raw_body or b"", hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, str(signature).strip())


def verify_paystack_transaction(*, reference: str) -> dict:
    ref = str(reference or "").strip()
    if not ref:
        return {
            "ok": False,
            "status": "",
            "amount": None,
            "currency": None,
            "reference": "",
            "raw": {},
        }

    raw = _request_json(
        "GET", f"{PAYSTACK_BASE}/transaction/verify/{ref}", body=None, timeout=25
    )

    ok = bool(raw.get("status"))
    data = raw.get("data") or {}

    tx_status = str(data.get("status") or "").strip().lower()
    amount = data.get("amount")
    try:
        amount_int = int(amount) if amount is not None else None
    except Exception:
        amount_int = None

    currency = data.get("currency")
    return {
        "ok": ok,
        "status": tx_status,
        "amount": amount_int,
        "currency": str(currency) if currency is not None else None,
        "reference": ref,
        "raw": raw,
    }