from decimal import Decimal
from datetime import date, timedelta

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.test import APIClient
from rest_framework import status

from products.models import Product, StockBatch
from pos.models import Cart, CartItem
from sales.models import Sale, SaleItem

User = get_user_model()


class POSBaseTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.cashier = User.objects.create_user(
            username="cashier",
            password="testpass123",
        )

        self.client.force_authenticate(user=self.cashier)

        self.product = Product.objects.create(
            sku="PARA-001",
            name="Paracetamol",
            unit_price=Decimal("100.00"),
            is_active=True,
        )

        self.batch = StockBatch.objects.create(
            product=self.product,
            batch_number="BATCH-001",
            expiry_date=date.today() + timedelta(days=365),
            quantity_received=50,
            quantity_remaining=50,
            is_active=True,
        )


class POSCartTests(POSBaseTestCase):

    def test_get_empty_cart(self):
        url = reverse("pos:active-cart")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(
            Decimal(response.data["total_amount"]),
            Decimal("0.00"),
        )

    def test_add_item_to_cart(self):
        url = reverse("pos:add-cart-item")

        response = self.client.post(
            url,
            {
                "product_id": str(self.product.id),
                "quantity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(
            Decimal(response.data["items"][0]["unit_price"]),
            Decimal("100.00"),
        )


class POSCheckoutTests(POSBaseTestCase):

    def test_checkout_success(self):
        cart = Cart.objects.get(user=self.cashier, is_active=True)

        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=3,
            unit_price=Decimal("100.00"),
        )

        url = reverse("pos:checkout")
        response = self.client.post(
            url,
            {"payment_method": "cash"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        sale = Sale.objects.first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.total_amount, Decimal("300.00"))

        sale_item = SaleItem.objects.first()
        self.assertEqual(sale_item.quantity, 3)

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 47)

        self.assertEqual(cart.items.count(), 0)

    def test_checkout_empty_cart_fails(self):
        url = reverse("pos:checkout")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
