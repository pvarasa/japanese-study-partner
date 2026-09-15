"""SPA fallback: client-side routes survive a reload in production serving."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import SPAStaticFiles


@pytest.fixture
def spa_client(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('app')")

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_root_serves_index(spa_client):
    res = spa_client.get("/")
    assert res.status_code == 200
    assert "root" in res.text


@pytest.mark.parametrize("path", ["/study", "/items?type=word&q=食べる", "/deep/nested/route"])
def test_client_routes_fall_back_to_index(spa_client, path):
    res = spa_client.get(path)
    assert res.status_code == 200
    assert "root" in res.text


def test_real_assets_are_served(spa_client):
    res = spa_client.get("/assets/app.js")
    assert res.status_code == 200
    assert "console.log" in res.text


def test_missing_asset_still_404s(spa_client):
    assert spa_client.get("/assets/missing.js").status_code == 404


def test_unknown_api_path_still_404s(spa_client):
    assert spa_client.get("/api/nope").status_code == 404
    assert spa_client.get("/api/health").json() == {"status": "ok"}


def test_non_get_is_not_answered_with_index(spa_client):
    assert spa_client.post("/study").status_code == 405
