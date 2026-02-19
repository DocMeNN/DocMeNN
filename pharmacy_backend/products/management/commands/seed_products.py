import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from products.models import (
    Category,
    Product,
    StockBatch,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed products, categories, and FIFO stock batches"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Seeding products and stock..."))

        # -------------------------------
        # CATEGORIES
        # -------------------------------
        categories = [
            "Antibiotics",
            "Pain Relief",
            "Vitamins",
            "Cold & Flu",
            "Antimalarial",
        ]

        category_objs = {}
        for name in categories:
            obj, _ = Category.objects.get_or_create(name=name)
            category_objs[name] = obj

        # -------------------------------
        # PRODUCTS
        # -------------------------------
        products_data = [
            ("AMOX-500", "Amoxicillin 500mg", "Antibiotics", 1200),
            ("PARA-500", "Paracetamol 500mg", "Pain Relief", 300),
            ("VITA-C", "Vitamin C 1000mg", "Vitamins", 800),
            ("FLU-STOP", "Flu Stop Syrup", "Cold & Flu", 1500),
            ("ART-LUM", "Artemether/Lumefantrine", "Antimalarial", 2500),
        ]

        product_objs = []

        for sku, name, cat, price in products_data:
            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": category_objs[cat],
                    "unit_price": price,
                },
            )
            product_objs.append(product)

        # -------------------------------
        # STOCK BATCHES (FIFO)
        # -------------------------------
        for product in product_objs:
            for i in range(2):  # 2 batches per product
                qty = random.randint(20, 50)
                expiry = date.today() + timedelta(days=180 + i * 60)

                StockBatch.objects.create(
                    product=product,
                    batch_number=f"BATCH-{i + 1}",
                    expiry_date=expiry,
                    quantity_received=qty,
                    quantity_remaining=qty,
                )

        self.stdout.write(
            self.style.SUCCESS("✅ Products and stock seeded successfully.")
        )
