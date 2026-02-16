from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


# ---------------- REGISTER ----------------
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
        ]

    def create(self, validated_data):
        role = validated_data.get("role", "customer")

        staff_roles = {"admin", "pharmacist", "cashier", "reception"}

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            role=role,
            is_staff=role in staff_roles,
        )

        return user


# ---------------- LOGIN (INPUT ONLY) ----------------
class LoginSerializer(serializers.Serializer):
    """
    Input validation only.
    Authentication is handled in the view.
    """
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )


# ---------------- USER OUTPUT ----------------
class UserSerializer(serializers.ModelSerializer):
    """
    Safe user representation for frontend consumption.
    """
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
        ]
