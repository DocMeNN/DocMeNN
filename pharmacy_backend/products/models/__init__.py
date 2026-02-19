"""
PATH: products/models/__init__.py

Products models export surface.

Compatibility:
- Tests expect ProductBatch to exist.
"""

from .category import Category
from .product import Product
from .stock_batch import StockBatch
from .stock_movement import StockMovement

# ---------------------------------------------------------
# Legacy alias (tests expect ProductBatch)
# ---------------------------------------------------------
ProductBatch = StockBatch

__all__ = [
    "Category",
    "Product",
    "StockBatch",
    "StockMovement",
    "ProductBatch",
]
