from __future__ import annotations

from io import BytesIO

from PIL import Image

from tailmate.adapters.db_gateway import gateway_app
from tailmate.contracts.constants import TRUSTED_USER_ID_HEADER
from tailmate.contracts.dog_profile import DogProfile


class FakeCursor:
    def __init__(self) -> None:
        self._last_statement = ""
        self._last_params: list[object] | None = None

    def execute(self, statement: str, params=None) -> None:
        self._last_statement = statement
        self._last_params = list(params) if params is not None else None

    def fetchone(self):
        if "SELECT attributes" in self._last_statement and self._last_params is not None:
            return ({"dog_id": "dog-1"},)
        return None

    def close(self) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self._cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


def build_jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (10, 10), color="blue")
    exif = Image.Exif()
    exif[0x010F] = "Tailmate Camera"
    exif[0x9003] = "2026:03:25 09:00:00"
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_gateway_strip_metadata_endpoint_removes_exif(monkeypatch) -> None:
    stored: dict[str, object] = {}

    class FakeBlobStore:
        def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
            stored["logical_path"] = logical_path
            stored["content_type"] = content_type
            stored["payload"] = payload
            return logical_path

        def resolve_resource(self, logical_path: str) -> str:
            return f"gs://tailmate-media/{logical_path}"

        def delete(self, logical_path: str) -> None:
            stored["deleted"] = logical_path

    class FakeDogProfileDBAdapter:
        def create_profile(self, request):
            raise AssertionError("Not used by this media-only test.")

        def load_profile(self, dog_id: str, *, requesting_user_id: str):
            return DogProfile(dog_id=dog_id, user_id=requesting_user_id, name="DouDou")

        def enrich_profile(self, request, extraction_result):
            raise AssertionError("Not used by this media-only test.")

    monkeypatch.setattr(gateway_app, "persist_media_asset", lambda *args, **kwargs: None)
    app = gateway_app.create_app(
        blob_store=FakeBlobStore(),
        db_connection_factory=lambda: FakeConnection(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
    )
    client = app.test_client()

    response = client.post(
        "/media/strip-metadata",
        data={
            "dog_id": "dog-1",
            "resource_kind": "images",
            "session_id": "session-1",
            "file": (BytesIO(build_jpeg_with_exif()), "sample.jpg"),
        },
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["logical_path"].startswith("dogs/dog-1/images/")
    assert payload["logical_path"].endswith(".jpg")
    assert payload["session_id"] == "session-1"
    with Image.open(BytesIO(stored["payload"])) as cleaned_image:
        assert cleaned_image.getexif().get(0x010F) is None
        assert cleaned_image.getexif().get(0x9003) is None
    logical_path = payload["logical_path"]
    assert payload["media_ref"] == f"gs://tailmate-media/{logical_path}"
    assert payload["resource_uri"] == payload["media_ref"]
    assert stored["logical_path"] == logical_path
