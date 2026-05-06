from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_assistant.serializers import AIQuerySerializer, AIResponseSerializer
from apps.ai_intelligence.assistant_service import run_hardened_assistant_chat
from apps.ai_intelligence.throttles import AssistantChatThrottle
from apps.common.ai_sanitize import sanitize_ai_error_message
from apps.common.exceptions import AIServiceException


class AIQueryView(APIView):
    """Legacy `/ai/query/` — same hardened assistant as `/ai/assistant/chat/`."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AssistantChatThrottle]
    serializer_class = AIQuerySerializer

    def post(self, request):
        serializer = AIQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = run_hardened_assistant_chat(
                user=request.user,
                prompt=serializer.validated_data["prompt"],
                conversation_id=None,
            )
        except AIServiceException as e:
            return Response(
                {"detail": sanitize_ai_error_message(str(e))},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            AIResponseSerializer(result).data,
            status=status.HTTP_200_OK,
        )
