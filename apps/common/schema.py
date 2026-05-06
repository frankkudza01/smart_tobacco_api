from drf_spectacular.openapi import AutoSchema
from rest_framework import serializers


class EmptySchemaSerializer(serializers.Serializer):
    """Fallback serializer used when APIView has no serializer_class."""


class LenientAutoSchema(AutoSchema):
    """
    Avoid schema-generation hard failures for plain APIViews that do not expose
    serializer_class/get_serializer.
    """

    def _get_serializer(self):
        try:
            serializer = super()._get_serializer()
            return serializer or EmptySchemaSerializer()
        except Exception:
            return EmptySchemaSerializer()
