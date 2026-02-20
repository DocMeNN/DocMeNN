# backend/create_admin.py

from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError

User = get_user_model()

EMAIL = "admin@tisdocme.com"
PASSWORD = "StrongPassword123!"

def run():
    try:
        if not User.objects.filter(email=EMAIL).exists():
            User.objects.create_superuser(
                email=EMAIL,
                password=PASSWORD,
            )
            print("Superuser created.")
        else:
            print("Superuser already exists.")
    except IntegrityError as e:
        print("Error:", e)
