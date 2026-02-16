# products/views/__init__.py

"""
Products views package exports.

Purpose:
- Central export point for router imports (ProductViewSet, StockBatchViewSet).
"""

from .product import ProductViewSet
from .stock_batch import StockBatchViewSet

__all__ = [
    "ProductViewSet",
    "StockBatchViewSet",
]
