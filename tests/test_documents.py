import io
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.common.enums import DocumentType
from apps.documents.models import Document
from apps.documents.services import verify_document


@pytest.mark.django_db
class TestDocumentUpload:
    def test_upload_document(self, authenticated_farmer_client, lot):
        url = reverse("document-list")
        file = SimpleUploadedFile("receipt.pdf", b"fake pdf content", content_type="application/pdf")
        data = {
            "lot": str(lot.id),
            "document_type": DocumentType.RECEIPT,
            "title": "Sale Receipt",
            "file": file,
        }
        response = authenticated_farmer_client.post(url, data, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["sha256_hash"] != ""
        assert response.data["document_type"] == DocumentType.RECEIPT

    def test_reject_invalid_file_type(self, authenticated_farmer_client, lot):
        url = reverse("document-list")
        file = SimpleUploadedFile("script.exe", b"bad content", content_type="application/x-msdownload")
        data = {
            "lot": str(lot.id),
            "document_type": DocumentType.RECEIPT,
            "title": "Bad File",
            "file": file,
        }
        response = authenticated_farmer_client.post(url, data, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestDocumentVerification:
    def test_verify_document_endpoint(self, authenticated_farmer_client, lot):
        file = SimpleUploadedFile("test.pdf", b"test content", content_type="application/pdf")
        doc = Document.objects.create(
            lot=lot,
            uploaded_by=lot.farm.owner,
            document_type=DocumentType.RECEIPT,
            title="Test Doc",
            file=file,
            file_name="test.pdf",
            mime_type="application/pdf",
            file_size=12,
            sha256_hash="dummy_hash",
        )

        url = reverse("document-verify", kwargs={"pk": doc.id})
        response = authenticated_farmer_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert "hash_match" in response.data
