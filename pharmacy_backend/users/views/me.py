from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# ---------------------------
# SERIALIZER
# ---------------------------


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    role = serializers.CharField()


# ---------------------------
# VIEW
# ---------------------------


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer  # 🔹 explicit

    @extend_schema(
        responses={200: MeSerializer},
        description="Get current authenticated user profile",
    )
    def get(self, request):
        user = request.user

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
            }
        )
