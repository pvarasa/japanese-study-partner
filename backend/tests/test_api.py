"""Smoke tests for non-AI API endpoints against an isolated SQLite DB."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---- Settings ---------------------------------------------------------------

def test_settings_default_is_n3(client):
    r = client.get("/api/settings/")
    assert r.status_code == 200
    assert r.json() == {"jlpt_level": "N3"}


def test_settings_update_and_persist(client):
    r = client.put("/api/settings/", json={"jlpt_level": "N2"})
    assert r.status_code == 200
    assert r.json() == {"jlpt_level": "N2"}
    # Persists across requests
    assert client.get("/api/settings/").json() == {"jlpt_level": "N2"}


def test_settings_rejects_invalid_level(client):
    r = client.put("/api/settings/", json={"jlpt_level": "N7"})
    assert r.status_code == 400


# ---- Items CRUD -------------------------------------------------------------

def _make_item(**overrides):
    base = {
        "type": "word",
        "japanese": "勉強",
        "reading": "べんきょう",
        "meaning": "study",
        "jlpt_level": "N5",
        "tags": ["daily"],
    }
    base.update(overrides)
    return base


def test_items_list_empty(client):
    r = client.get("/api/items/")
    assert r.status_code == 200
    assert r.json() == []


def test_items_create_and_fetch(client):
    r = client.post("/api/items/", json=_make_item())
    assert r.status_code == 200
    item = r.json()
    assert item["japanese"] == "勉強"
    assert item["meaning"] == "study"
    assert item["tags"] == ["daily"]

    r = client.get(f"/api/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["japanese"] == "勉強"


def test_items_update_partial(client):
    item = client.post("/api/items/", json=_make_item()).json()
    r = client.put(f"/api/items/{item['id']}", json={"meaning": "studying hard"})
    assert r.status_code == 200
    assert r.json()["meaning"] == "studying hard"
    # Unchanged fields stay intact
    assert r.json()["japanese"] == "勉強"


def test_items_delete(client):
    item = client.post("/api/items/", json=_make_item()).json()
    assert client.delete(f"/api/items/{item['id']}").status_code == 200
    assert client.get(f"/api/items/{item['id']}").status_code == 404


def test_items_search_filters_by_text(client):
    client.post("/api/items/", json=_make_item(japanese="勉強", meaning="study"))
    client.post("/api/items/", json=_make_item(japanese="食べる", reading="たべる", meaning="to eat"))
    r = client.get("/api/items/?search=eat")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["japanese"] == "食べる"


def test_items_filter_by_type(client):
    client.post("/api/items/", json=_make_item(type="word", japanese="犬", meaning="dog"))
    client.post("/api/items/", json=_make_item(type="grammar", japanese="〜てしまう", meaning="completion"))
    r = client.get("/api/items/?type=grammar")
    assert [i["type"] for i in r.json()] == ["grammar"]


def test_items_missing_returns_404(client):
    assert client.get("/api/items/99999").status_code == 404
    assert client.put("/api/items/99999", json={"meaning": "x"}).status_code == 404
    assert client.delete("/api/items/99999").status_code == 404


# ---- Study / SRS ------------------------------------------------------------

def test_due_items_includes_newly_created(client):
    # Newly created items are due immediately (srs_due defaults to now)
    item = client.post("/api/items/", json=_make_item()).json()
    r = client.get("/api/study/due")
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert item["id"] in ids


def test_review_updates_srs_fields(client):
    item = client.post("/api/items/", json=_make_item()).json()
    r = client.post("/api/study/review", json={"item_id": item["id"], "rating": "good"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["interval_days"] == 1.0  # "good" on a new item → 1 day

    updated = client.get(f"/api/items/{item['id']}").json()
    assert updated["srs_reviews"] == 1
    assert updated["srs_correct"] == 1


def test_review_again_doesnt_increment_correct(client):
    item = client.post("/api/items/", json=_make_item()).json()
    client.post("/api/study/review", json={"item_id": item["id"], "rating": "again"})
    updated = client.get(f"/api/items/{item['id']}").json()
    assert updated["srs_reviews"] == 1
    assert updated["srs_correct"] == 0


def test_dashboard_shape(client):
    client.post("/api/items/", json=_make_item())
    r = client.get("/api/study/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["total_items"] == 1
    assert body["due_today"] == 1
    assert "weak_items" in body
    assert "recent_items" in body
    assert isinstance(body["streak_days"], int)


def test_session_start_and_end(client):
    r = client.post("/api/study/session/start?mode=flashcard_jp")
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    r = client.post(
        f"/api/study/session/{session_id}/end?items_reviewed=3&items_correct=2"
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_end_unknown_session_404(client):
    r = client.post("/api/study/session/99999/end?items_reviewed=0&items_correct=0")
    assert r.status_code == 404
