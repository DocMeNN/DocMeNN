from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User

# ---------------------------
# SERIALIZERS (LOCAL, SIMPLE)
# ---------------------------


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    role = serializers.CharField(required=False)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class LoginResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user_id = serializers.UUIDField()
    email = serializers.EmailField()
    role = serializers.CharField()


# ---------------------------
# VIEWS
# ---------------------------


class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer  # 🔹 explicit

    @extend_schema(
        request=RegisterSerializer,
        responses={201: dict},
        description="Register a new user account",
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            role=data.get("role", "customer"),
        )

        return Response(
            {"message": "User registered successfully"},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer  # 🔹 explicit

    @extend_schema(
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
        description="Authenticate user with email and password",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = authenticate(
            request=request,
            email=email,
            password=password,
        )

        if not user:
            return Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "message": "Login successful",
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
            }
        )
