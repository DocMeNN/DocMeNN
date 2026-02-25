# public/services/paystack.py
from __future__ import annotations

import hashlib
import hmac
import json
import os
import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger("payments")

PAYSTACK_BASE = "https://api.paystack.co"


def _paystack_cfg() -> dict:
    payments = getattr(settings, "PAYMENTS", {}) or {}
    cfg = (payments.get("PAYSTACK") or {}) if isinstance(payments, dict) else {}
    if isinstance(cfg, dict):
        return cfg
    return {}


def _get_secret_key() -> str:
    cfg = _paystack_cfg()
    sk = (cfg.get("SECRET_KEY") or "").strip()

    if not sk:
        sk = (os.environ.get("PAYSTACK_SECRET_KEY") or "").strip()

    if not sk:
        logger.critical("Paystack SECRET_KEY not configured")
        raise RuntimeError(
            "PAYSTACK SECRET_KEY is not configured. "
            "Expected settings.PAYMENTS['PAYSTACK']['SECRET_KEY'] or env PAYSTACK_SECRET_KEY."
        )

    return sk


def _to_kobo(amount_naira: Decimal) -> int:
    try:
        naira = Decimal(str(amount_naira))
    except (InvalidOperation, ValueError, TypeError) as exc:
        logger.error("Invalid amount passed to _to_kobo", extra={"amount": str(amount_naira)})
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
            "User-Agent": "PharmacyBackend/1.0",
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
            pass

        parsed_any = _parse_json_or_text(raw)

        logger.error(
            "Paystack HTTPError",
            extra={
                "status_code": getattr(e, "code", None),
                "response_preview": _safe_preview(raw),
            },
        )

        raise RuntimeError(f"Paystack HTTPError: {e.code}") from e

    except URLError as e:
        logger.error("Paystack URLError", extra={"error": str(e)})
        raise RuntimeError(f"Paystack URLError: {e}") from e

    except Exception:
        logger.exception("Unexpected Paystack request failure")
        raise RuntimeError("Paystack request failed")

    if parsed_any.get("kind") != "json":
        preview = _safe_preview(parsed_any.get("raw") or "")
        logger.error("Paystack returned non-JSON response", extra={"response_preview": preview})
        raise RuntimeError("Paystack returned non-JSON response")

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

    logger.info("Initializing Paystack transaction", extra={"reference": reference})

    parsed = _request_json(
        "POST", f"{PAYSTACK_BASE}/transaction/initialize", body=payload, timeout=25
    )

    if not parsed.get("status"):
        logger.error(
            "Paystack initialization rejected",
            extra={"reference": reference, "message": parsed.get("message")},
        )
        raise RuntimeError(parsed.get("message") or "Paystack init rejected")

    return parsed.get("data") or {}


def verify_paystack_signature(*, raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        logger.warning("Paystack webhook received without signature")
        return False

    sk = _get_secret_key().encode("utf-8")
    computed = hmac.new(sk, raw_body or b"", hashlib.sha512).hexdigest()

    valid = hmac.compare_digest(computed, str(signature).strip())
    if not valid:
        logger.warning("Invalid Paystack signature received")

    return valid


def verify_paystack_transaction(*, reference: str) -> dict:
    ref = str(reference or "").strip()

    if not ref:
        logger.warning("Paystack verification called with empty reference")
        return {
            "ok": False,
            "status": "",
            "amount": None,
            "currency": None,
            "reference": "",
            "raw": {},
        }

    logger.info("Verifying Paystack transaction", extra={"reference": ref})

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

    if not ok or tx_status != "success":
        logger.warning(
            "Paystack verification not successful",
            extra={"reference": ref, "status": tx_status},
        )

    return {
        "ok": ok,
        "status": tx_status,
        "amount": amount_int,
        "currency": str(currency) if currency is not None else None,
        "reference": ref,
        "raw": raw,
    }