"""JSON auth API. Session cookies + CSRF; see docs/auth.md."""

from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.email import send_email
from apps.core.throttling import AuthRateThrottle

from . import services
from .serializers import DeleteAccountSerializer, LoginSerializer, SignupSerializer, UserSerializer


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the ``csrftoken`` cookie; the token is also returned for convenience."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: {"type": "object", "properties": {"csrfToken": {"type": "string"}}}})
    def get(self, request: Request) -> Response:
        return Response({"csrfToken": get_token(request._request)})


# DRF exempts views from CSRF for anonymous callers; credential endpoints opt back in
# so a malicious site cannot log a victim in to an attacker-controlled account.
@method_decorator(csrf_protect, name="dispatch")
class SignupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(request=SignupSerializer, responses={201: UserSerializer})
    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = services.register_user(request._request, data["email"], data["password"], data["name"])
        except services.EmailTaken:
            return Response(
                {"email": ["A user with this email already exists."]}, status=status.HTTP_400_BAD_REQUEST
            )
        body = dict(UserSerializer(user).data)
        if services.verification_required():
            body["verification_required"] = True
        else:
            login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(body, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.authenticate_user(request._request, **serializer.validated_data)
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=UserSerializer, responses=UserSerializer)
    def patch(self, request: Request) -> Response:
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(request=DeleteAccountSerializer, responses={204: None})
    def delete(self, request: Request) -> Response:
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["password"]):
            return Response({"password": ["Incorrect password."]}, status=status.HTTP_400_BAD_REQUEST)
        email = user.email
        logout(request._request)
        user.delete()
        send_email(email, "Account deleted", "account_deleted", {"email": email})
        return Response(status=status.HTTP_204_NO_CONTENT)
