from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import CanRunFarmProvenanceChecks
from apps.common.schema import EmptySchemaSerializer
from apps.provenance.services import get_lot_provenance, run_farm_provenance_checks


class LotProvenanceView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request, lot_id):
        provenance = get_lot_provenance(lot_id, queried_by=request.user)
        if provenance is None:
            return Response({"detail": "Lot not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(provenance, status=status.HTTP_200_OK)


class FarmProvenanceChecksRunView(APIView):
    """
    Farm provenance + document validity checks (grower on own farm, buyer,
    auditor, or admin). Farm scope is enforced in run_farm_provenance_checks.
    """

    permission_classes = [IsAuthenticated, CanRunFarmProvenanceChecks]
    serializer_class = EmptySchemaSerializer

    def post(self, request, farm_id):
        summary = run_farm_provenance_checks(farm_id=farm_id, queried_by=request.user)
        if not summary.get("ok"):
            detail = summary.get("detail", "Failed to run checks.")
            if detail == "Farm not found.":
                return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)
            if detail == "Forbidden":
                return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(summary, status=status.HTTP_200_OK)
