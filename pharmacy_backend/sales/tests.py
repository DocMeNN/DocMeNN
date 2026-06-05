from django.test import TestCase

# Create your tests here.
# sales/tests.py
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from products.models import Product

User = get_user_model()

class SalesAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='cashier@example.com', password='pass', role='cashier')
        self.prod = Product.objects.create(sku='SKU1', name='TestProduct', unit_price=100, stock=10)

    def test_create_sale_requires_auth(self):
        url = reverse('sale-create')
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_create_sale_decrements_stock(self):
        self.client.force_authenticate(self.user)
        url = reverse('sale-create')
        payload = {
            "items": [
                {"product": str(self.prod.id), "quantity": 2, "unit_price": "100.00", "total_price": "200.00"}
            ],
            "payment_method": "cash"
        }
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock, 8)
