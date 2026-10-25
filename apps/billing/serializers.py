from rest_framework import serializers

from .models import Plan


class PlanSerializer(serializers.ModelSerializer):
    purchasable = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = ["slug", "name", "limits", "purchasable"]

    def get_purchasable(self, obj: Plan) -> bool:
        return bool(obj.stripe_price_id)


class CheckoutSerializer(serializers.Serializer):
    plan = serializers.SlugField()
