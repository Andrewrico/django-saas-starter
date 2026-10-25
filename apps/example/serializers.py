import json

from rest_framework import serializers

from .models import Project

MAX_DATA_BYTES = 4096


class ProjectSerializer(serializers.ModelSerializer):
    # No ``owner`` field at all: it can never be set from a payload.
    class Meta:
        model = Project
        fields = ["id", "name", "description", "data", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name may not be blank.")
        return value

    def validate_data(self, value: object) -> object:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a JSON object.")
        if len(json.dumps(value).encode()) > MAX_DATA_BYTES:
            raise serializers.ValidationError(f"Must be at most {MAX_DATA_BYTES} bytes when serialised.")
        return value
