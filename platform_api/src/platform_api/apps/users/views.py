"""Views for the users app."""

from rest_framework import permissions
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import UserSerializer


class CurrentUserView(GenericAPIView):  # type: ignore[type-arg]
    """Return the currently authenticated user."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request: Request) -> Response:
        """Handle GET requests for the current user."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
