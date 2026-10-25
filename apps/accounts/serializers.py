from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, style={"input_type": "password"})
    name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate(self, attrs: dict) -> dict:
        validate_password(attrs["password"], User(email=attrs["email"], name=attrs.get("name", "")))
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class UserSerializer(serializers.ModelSerializer):
    plan = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "name", "date_joined", "plan"]
        read_only_fields = ["id", "email", "date_joined", "plan"]

    def get_plan(self, obj: User) -> str:
        from apps.billing.limits import get_plan

        return get_plan(obj).slug


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
