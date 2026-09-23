import random
import sys
import time
from types import SimpleNamespace
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from web.app import create_app
from web.services import oss_jobs
from web.services import oss_asset_provider as oss_asset_provider_module
from web.services.oss_asset_provider import OssAssetProvider


class _Object:
    def __init__(self, key: str):
        self.key = key
        self.size = 10
        self.content_type = "image/jpeg"


class _Listing:
    is_truncated = False
    next_marker = ""

    def __init__(self, *, prefixes=None, objects=None):
        self.prefix_list = prefixes or []
        self.object_list = objects or []


class _FakeBucket:
    def __init__(self):
        self.keys = [
            "图片素材库/寿司/三文鱼寿司/a.jpg",
            "图片素材库/寿司/三文鱼寿司/b.png",
            "图片素材库/寿司/金枪鱼寿司/a.jpg",
            "图片素材库/寿司/鳗鱼寿司/a.webp",
        ]

    def list_objects(self, prefix="", delimiter=None, marker="", max_keys=1000):
        keys = [key for key in self.keys if key.startswith(prefix)]
        if delimiter:
            prefixes = sorted({key[: key.find(delimiter, len(prefix)) + 1] for key in keys if delimiter in key[len(prefix):]})
            return _Listing(prefixes=prefixes)
        return _Listing(objects=[_Object(key) for key in keys])


def test_oss_provider_selects_different_dish_folders(monkeypatch):
    monkeypatch.setattr("web.services.oss_asset_provider.OSS_ASSET_PREFIX", "图片素材库")
    provider = OssAssetProvider(_FakeBucket())

    diagnostics = provider.diagnose_layout()
    assert diagnostics["layout_ready"] is True
    assert diagnostics["categories"][0]["dish_folder_count"] == 3

    selected = provider.select_unique_assets([{"category": "寿司", "count": 3}], random.Random(7))

    assert len(selected) == 3
    assert len({item["dish_name"] for item in selected}) == 3
    assert all(item["object_key"].startswith("图片素材库/寿司/") for item in selected)


def test_oss_provider_uses_ecs_ram_role_metadata_endpoint(monkeypatch):
    captured = {}

    class _Credentials:
        def __init__(self, auth_host):
            captured["auth_host"] = auth_host

    fake_oss2 = SimpleNamespace(
        credentials=SimpleNamespace(EcsRamRoleCredentialsProvider=_Credentials),
        ProviderAuth=lambda credentials: credentials,
        Bucket=lambda auth, endpoint, bucket_name: (auth, endpoint, bucket_name),
    )
    monkeypatch.setitem(sys.modules, "oss2", fake_oss2)
    monkeypatch.setattr(oss_asset_provider_module, "OSS_BUCKET", "patrick0619")
    monkeypatch.setattr(oss_asset_provider_module, "OSS_ENDPOINT", "https://oss-cn-shenzhen.aliyuncs.com")
    monkeypatch.setattr(oss_asset_provider_module, "OSS_RAM_ROLE_NAME", "EcsOssAssetReadOnly")

    OssAssetProvider().bucket

    assert captured["auth_host"] == (
        "http://100.100.100.200/latest/meta-data/ram/security-credentials/"
        "EcsOssAssetReadOnly"
    )


def test_oss_provider_discovers_ecs_ram_role_name(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"ActualAttachedRole\n"

    class _Credentials:
        def __init__(self, auth_host):
            captured["auth_host"] = auth_host

    fake_oss2 = SimpleNamespace(
        credentials=SimpleNamespace(EcsRamRoleCredentialsProvider=_Credentials),
        ProviderAuth=lambda credentials: credentials,
        Bucket=lambda auth, endpoint, bucket_name: (auth, endpoint, bucket_name),
    )
    monkeypatch.setitem(sys.modules, "oss2", fake_oss2)
    monkeypatch.setattr(oss_asset_provider_module, "OSS_BUCKET", "patrick0619")
    monkeypatch.setattr(oss_asset_provider_module, "OSS_ENDPOINT", "https://oss-cn-shenzhen.aliyuncs.com")
    monkeypatch.setattr(oss_asset_provider_module, "OSS_RAM_ROLE_NAME", "")
    monkeypatch.setattr(oss_asset_provider_module, "urlopen", lambda *_args, **_kwargs: _Response())

    OssAssetProvider().bucket

    assert captured["auth_host"].endswith("/ActualAttachedRole")


class _FakeJobProvider:
    def list_categories(self):
        return ["寿司", "主菜"]

    def select_unique_assets(self, selections, rng):
        assets = []
        for selection in selections:
            for index in range(int(selection["count"])):
                assets.append({
                    "asset_id": f"asset_{len(assets) + 1:03d}",
                    "category": selection["category"],
                    "dish_name": f"{selection['category']}-{index + 1}",
                    "object_key": f"图片素材库/{selection['category']}/dish-{index + 1}/image.jpg",
                    "filename": "image.jpg",
                    "suffix": ".jpg",
                    "size": 100,
                    "content_type": "image/jpeg",
                    "status": "selected",
                })
        return assets

    def download_asset(self, asset, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1600, 900), "#d9b38c").save(destination, "JPEG")


def _wait_for_status(client, job_id: str, expected: str, attempts: int = 40):
    for _ in range(attempts):
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload.get("status") == expected:
            return payload
        if payload.get("status") == "error":
            raise AssertionError(payload)
        time.sleep(0.025)
    raise AssertionError(client.get(f"/api/jobs/{job_id}").json())


def test_oss_job_downloads_normalizes_and_keeps_review_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(oss_jobs, "OSS_JOB_ROOT", tmp_path / "oss-jobs")
    monkeypatch.setattr(oss_jobs, "OssAssetProvider", _FakeJobProvider)
    client = TestClient(create_app())

    response = client.post("/api/jobs", json={"selections": [{"category": "寿司", "count": 2}], "seed": 1})

    assert response.status_code == 200
    queued = response.json()
    assert queued["status"] == "queued"
    payload = _wait_for_status(client, queued["job_id"], "awaiting_review")
    assert payload["asset_count"] == 2
    assert payload["output_resolution"] == {"width": 1080, "height": 1920}
    assert all(asset["normalized_url"].startswith("/api/jobs/") for asset in payload["assets"])

    normalized = client.get(payload["assets"][0]["normalized_url"])
    assert normalized.status_code == 200
    normalized_path = tmp_path / "normalized.jpg"
    normalized_path.write_bytes(normalized.content)
    with Image.open(normalized_path) as image:
        assert image.size == (1080, 1920)

    approved = client.post(f"/api/jobs/{queued['job_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"


def test_oss_job_request_limits_are_rejected():
    response = TestClient(create_app()).post(
        "/api/jobs",
        json={"selections": [{"category": "寿司", "count": 0}]},
    )

    assert response.status_code == 400
