from rest_framework.throttling import UserRateThrottle


class AssistantChatThrottle(UserRateThrottle):
    scope = "assistant_chat"
