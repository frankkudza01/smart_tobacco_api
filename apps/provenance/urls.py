from django.urls import path

from apps.provenance.views import FarmProvenanceChecksRunView, LotProvenanceView

urlpatterns = [
    path("lots/<uuid:lot_id>/", LotProvenanceView.as_view(), name="lot-provenance"),
    path(
        "farms/<uuid:farm_id>/checks/run/",
        FarmProvenanceChecksRunView.as_view(),
        name="farm-provenance-checks-run",
    ),
]
