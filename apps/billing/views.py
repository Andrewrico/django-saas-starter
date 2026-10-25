from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .limits import get_plan
from .models import Plan
from .serializers import CheckoutSerializer, PlanSerializer
from .stripe_client import billing_enabled


def _disabled() -> Response:
    return Response({"detail": "Billing is not enabled."}, status=status.HTTP_404_NOT_FOUND)


class PlanListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PlanSerializer(many=True))
    def get(self, request: Request) -> Response:
        plans = Plan.objects.filter(is_public=True)
        return Response(PlanSerializer(plans, many=True).data)


class SubscriptionView(APIView):
    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        plan = get_plan(request.user)
        return Response({"plan": plan.slug, "limits": plan.limits, "billing_enabled": billing_enabled()})


class CheckoutView(APIView):
    @extend_schema(
        request=CheckoutSerializer,
        responses={200: {"type": "object", "properties": {"url": {"type": "string"}}}},
    )
    def post(self, request: Request) -> Response:
        if not billing_enabled():
            return _disabled()
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            url = services.create_checkout_session(request.user, serializer.validated_data["plan"])
        except services.BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"url": url})


class PortalView(APIView):
    @extend_schema(
        request=None, responses={200: {"type": "object", "properties": {"url": {"type": "string"}}}}
    )
    def post(self, request: Request) -> Response:
        if not billing_enabled():
            return _disabled()
        try:
            url = services.create_portal_session(request.user)
        except services.BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"url": url})


@extend_schema(exclude=True)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def webhook(request: Request) -> Response:
    """Stripe webhook. Signature-verified, idempotent, 404 while billing is off.

    Stripe sends its own signed header instead of a CSRF token, so DRF with no
    authentication classes (which skips CSRF) is the right tool here.
    """
    if not billing_enabled():
        return _disabled()
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = services.construct_event(request.body, signature)
    except ValueError:
        return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)
    created = services.handle_event(event)
    return Response({"received": True, "duplicate": not created})
