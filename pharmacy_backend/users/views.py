# users/views.py
"""
USER AUTH VIEWS

Security hardening:
- Targeted throttling for high-risk endpoints:
  - Register (anon)
  - Login (anon)
  - Me (user)
- Remove csrf_exempt for JWT login (not needed; JWT uses Authorization header)
  Keeping CSRF exempt can create a false sense of safety and broadens surface.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer, RegisterSerializer, UserSerializer

User = get_user_model()


# ---------------- THROTTLES (TARGETED) ----------------
class RegisterAnonThrottle(AnonRateThrottle):
    """
    Anonymous registration throttling.
    Uses REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['anon'].
    """
    scope = "anon"


class LoginAnonThrottle(AnonRateThrottle):
    """
    Anonymous login throttling.
    Uses REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['anon'].
    """
    scope = "anon"


class MeUserThrottle(UserRateThrottle):
    """
    Authenticated user throttling for /me/.
    Uses REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['user'].
    """
    scope = "user"


# ---------------- REGISTER ----------------
class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterAnonThrottle]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "message": "User registered successfully",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------- LOGIN (JWT + EMAIL) ----------------
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginAnonThrottle]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "Invalid email or password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(password):
            return Response(
                {"detail": "Invalid email or password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------- CURRENT USER ----------------
class MeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [MeUserThrottle]

    def get(self, request):
        return Response(
            {
                "authenticated": True,
                "user": UserSerializer(request.user).data,
            },
            status=status.HTTP_200_OK,
        )
