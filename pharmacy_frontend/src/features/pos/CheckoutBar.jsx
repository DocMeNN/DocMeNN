// src/features/pos/CheckoutBar.jsx

import { useEffect, useRef, useState } from "react";

/**
 * ======================================================
 * PATH: src/features/pos/CheckoutBar.jsx
 * ======================================================
 *
 * CheckoutBar (UI-only)
 * ------------------------------------------------------
 * - Pure UI component
 * - Emits checkout intent only (opens Payment modal in PosPage)
 * - No business logic
 * - Safe against double submission
 * ======================================================
 */
export default function CheckoutBar({ onCheckout, disabled = false }) {
  const [submitting, setSubmitting] = useState(false);
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (disabled) {
      setSubmitting(false);
      inFlightRef.current = false;
    }
  }, [disabled]);

  const locked = disabled || submitting;

  const handleClick = async () => {
    if (locked) return;

    // Extra guard against double fire
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    setSubmitting(true);
    try {
      await onCheckout?.();
    } finally {
      setSubmitting(false);
      inFlightRef.current = false;
    }
  };

  return (
    <button
      type="button"
      disabled={locked}
      onClick={handleClick}
      className="
        w-full mt-4 py-3 rounded
        bg-blue-600 text-white font-semibold
        hover:bg-blue-700
        disabled:opacity-40 disabled:cursor-not-allowed
        transition
      "
      aria-disabled={locked}
    >
      {submitting ? "Processing Checkout…" : "Complete Checkout"}
    </button>
  );
}
