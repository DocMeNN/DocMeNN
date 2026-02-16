# sales/views/public_checkout.py

"""
DEPRECATED (COMPAT WRAPPER)

We have migrated public endpoints into the modular `public/` Django app.

Keep this module temporarily so:
- old imports still work
- old references in code/tests don’t break

Canonical implementation now lives in:
- public/views/checkout.py
"""

from public.views.checkout import (  # noqa: F401
    PublicCheckoutView,
    PublicReceiptView,
)
