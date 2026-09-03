"""Smoke tests for non-AI API endpoints against an isolated SQLite DB."""
import pytest


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


def test_practice_items_ignores_due_date(client):
    item = client.post("/api/items/", json=_make_item()).json()
    # Push the item's due date far into the future so it's not "due", the way
    # a real review would after a few successful ratings.
    client.post("/api/study/review", json={"item_id": item["id"], "rating": "good"})
    assert client.get("/api/study/due").json() == []

    ids = [it["id"] for it in client.get("/api/study/practice").json()]
    assert item["id"] in ids


def test_practice_items_excludes_suspended(client):
    item = client.post("/api/items/", json=_make_item()).json()
    client.post(f"/api/items/{item['id']}/suspend")
    ids = [it["id"] for it in client.get("/api/study/practice").json()]
    assert item["id"] not in ids


def test_practice_review_does_not_change_srs_fields(client):
    item = client.post("/api/items/", json=_make_item()).json()
    before = client.get(f"/api/items/{item['id']}").json()

    r = client.post(
        "/api/study/review",
        json={"item_id": item["id"], "rating": "good", "practice": True},
    )
    assert r.status_code == 200

    after = client.get(f"/api/items/{item['id']}").json()
    assert after["srs_reviews"] == before["srs_reviews"]
    assert after["srs_correct"] == before["srs_correct"]
    assert after["srs_due"] == before["srs_due"]


def test_practice_review_still_advances_session_counters(client):
    item = client.post("/api/items/", json=_make_item()).json()
    sid = client.post("/api/study/session/start?mode=practice_flashcard_jp").json()["session_id"]
    client.post(
        "/api/study/review",
        json={"item_id": item["id"], "rating": "good", "session_id": sid, "practice": True},
    )
    body = client.get("/api/study/dashboard").json()
    # Not a graded mode, so it counts toward activity but not accuracy.
    assert body["studied_today"] == 1
    assert body["accuracy_today"] == 0


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

    r = client.post(f"/api/study/session/{session_id}/end")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_end_unknown_session_404(client):
    r = client.post("/api/study/session/99999/end")
    assert r.status_code == 404


def _record_session(client, mode, reviewed, correct, hard=0):
    """Synthesise a completed session. Counters only move through /progress."""
    sid = client.post(f"/api/study/session/start?mode={mode}").json()["session_id"]
    client.post(
        f"/api/study/session/{sid}/progress",
        json={"reviewed": reviewed, "correct": correct, "hard": hard},
    )
    client.post(f"/api/study/session/{sid}/end")


def test_accuracy_reflects_graded_sessions(client):
    _record_session(client, "flashcard_jp", reviewed=4, correct=2)
    assert client.get("/api/study/dashboard").json()["accuracy_today"] == 50.0


def test_converse_excluded_from_accuracy(client):
    """Conversation turns aren't graded, so they must not skew accuracy."""
    _record_session(client, "flashcard_jp", reviewed=4, correct=2)   # 50%
    _record_session(client, "converse", reviewed=6, correct=6)       # not graded

    body = client.get("/api/study/dashboard").json()
    assert body["accuracy_today"] == 50.0   # unchanged by the converse session
    assert body["studied_today"] == 10      # but total activity still counts it


def test_accuracy_zero_when_only_ungraded_activity(client):
    _record_session(client, "converse", reviewed=5, correct=5)
    body = client.get("/api/study/dashboard").json()
    assert body["accuracy_today"] == 0
    assert body["studied_today"] == 5


def test_converse_session_still_counts_for_streak(client):
    _record_session(client, "converse", reviewed=3, correct=1)
    assert client.get("/api/study/dashboard").json()["streak_days"] == 1


# ---- Incremental session recording -------------------------------------------
# Counters used to be written only when a session ran to completion, so
# abandoning one part-way recorded nothing at all.

def test_review_with_session_id_advances_counters(client):
    item = client.post("/api/items/", json=_make_item()).json()
    sid = client.post("/api/study/session/start?mode=flashcard_jp").json()["session_id"]

    client.post("/api/study/review", json={"item_id": item["id"], "rating": "good", "session_id": sid})
    body = client.get("/api/study/dashboard").json()
    assert body["studied_today"] == 1
    assert body["accuracy_today"] == 100.0


def test_abandoned_session_keeps_its_progress(client):
    """No /end call at all — the reviews already done must still count."""
    item = client.post("/api/items/", json=_make_item()).json()
    sid = client.post("/api/study/session/start?mode=flashcard_jp").json()["session_id"]
    for rating in ("good", "again", "hard"):
        client.post("/api/study/review", json={"item_id": item["id"], "rating": rating, "session_id": sid})

    body = client.get("/api/study/dashboard").json()
    assert body["studied_today"] == 3
    # Strict accuracy: only the "good" counts, "hard" is tracked separately.
    assert body["accuracy_today"] == pytest.approx(33.3, abs=0.1)


def test_review_without_session_id_records_no_session_progress(client):
    item = client.post("/api/items/", json=_make_item()).json()
    client.post("/api/study/review", json={"item_id": item["id"], "rating": "good"})
    assert client.get("/api/study/dashboard").json()["studied_today"] == 0


def test_review_ignores_a_session_belonging_to_another_user(client):
    item = client.post("/api/items/", json=_make_item()).json()
    sid = client.post(
        "/api/study/session/start?mode=flashcard_jp", headers={"X-User-ID": "someone"}
    ).json()["session_id"]

    r = client.post("/api/study/review", json={"item_id": item["id"], "rating": "good", "session_id": sid})
    assert r.status_code == 200  # the review itself still lands
    assert client.get("/api/study/dashboard", headers={"X-User-ID": "someone"}).json()["studied_today"] == 0


def test_session_progress_endpoint_accumulates(client):
    sid = client.post("/api/study/session/start?mode=converse").json()["session_id"]
    client.post(f"/api/study/session/{sid}/progress", json={"reviewed": 1, "correct": 1})
    r = client.post(f"/api/study/session/{sid}/progress", json={"reviewed": 1})
    assert r.json()["items_reviewed"] == 2
    assert client.get("/api/study/dashboard").json()["studied_today"] == 2


def test_progress_on_unknown_session_404s(client):
    r = client.post("/api/study/session/99999/progress", json={"reviewed": 1})
    assert r.status_code == 404


def test_end_preserves_accumulated_progress(client):
    """Closing a session must not disturb what the reviews already recorded."""
    item = client.post("/api/items/", json=_make_item()).json()
    sid = client.post("/api/study/session/start?mode=flashcard_jp").json()["session_id"]
    client.post("/api/study/review", json={"item_id": item["id"], "rating": "good", "session_id": sid})

    assert client.post(f"/api/study/session/{sid}/end").status_code == 200
    assert client.get("/api/study/dashboard").json()["studied_today"] == 1


# ---- Leeches -----------------------------------------------------------------

def _make_leech(client, **overrides):
    """Fail an item enough times to trip the leech threshold."""
    item = client.post("/api/items/", json=_make_item(**overrides)).json()
    for _ in range(8):
        client.post("/api/study/review", json={"item_id": item["id"], "rating": "again"})
    return client.get(f"/api/items/{item['id']}").json()


def test_repeated_failure_auto_suspends(client):
    item = _make_leech(client)
    assert item["suspended"] is True
    assert item["is_leech"] is True
    assert item["srs_lapses"] == 8


def test_suspended_items_are_excluded_from_due(client):
    leech = _make_leech(client)
    healthy = client.post("/api/items/", json=_make_item(japanese="猫")).json()

    ids = [it["id"] for it in client.get("/api/study/due").json()]
    assert healthy["id"] in ids
    assert leech["id"] not in ids


def test_dashboard_reports_leeches_and_excludes_them_from_due_count(client):
    _make_leech(client)
    body = client.get("/api/study/dashboard").json()
    assert body["suspended_count"] == 1
    assert len(body["leeches"]) == 1
    assert body["due_today"] == 0
    # A suspended card shouldn't also occupy a "needs practice" slot.
    assert body["weak_items"] == []


def test_manual_suspend_and_unsuspend_round_trip(client):
    item = client.post("/api/items/", json=_make_item()).json()
    assert client.post(f"/api/items/{item['id']}/suspend").json()["suspended"] is True
    assert client.get("/api/study/due").json() == []

    assert client.post(f"/api/items/{item['id']}/unsuspend").json()["suspended"] is False
    assert len(client.get("/api/study/due").json()) == 1


def test_unsuspend_resets_history_so_the_card_doesnt_instantly_relapse(client):
    leech = _make_leech(client)
    restored = client.post(f"/api/items/{leech['id']}/unsuspend").json()
    assert restored["srs_reviews"] == 0
    assert restored["srs_lapses"] == 0
    assert restored["is_leech"] is False


def test_unsuspend_can_keep_history(client):
    leech = _make_leech(client)
    restored = client.post(f"/api/items/{leech['id']}/unsuspend?reset=false").json()
    assert restored["suspended"] is False
    assert restored["srs_reviews"] == 8


def test_items_filter_by_suspended(client):
    leech = _make_leech(client)
    client.post("/api/items/", json=_make_item(japanese="猫"))

    suspended = client.get("/api/items/?suspended=true").json()
    assert [i["id"] for i in suspended] == [leech["id"]]
    assert len(client.get("/api/items/?suspended=false").json()) == 1


def test_suspend_404s_across_users(client):
    item = client.post("/api/items/", json=_make_item()).json()
    r = client.post(f"/api/items/{item['id']}/suspend", headers={"X-User-ID": "other"})
    assert r.status_code == 404


# ---- History -----------------------------------------------------------------

def test_history_is_empty_without_activity(client):
    assert client.get("/api/study/history").json() == []


def test_history_aggregates_graded_sessions_for_today(client):
    _record_session(client, "flashcard_jp", reviewed=6, correct=3)
    _record_session(client, "cloze", reviewed=4, correct=3)

    history = client.get("/api/study/history").json()
    assert len(history) == 1
    assert history[0]["reviewed"] == 10
    assert history[0]["correct"] == 6
    assert history[0]["accuracy"] == 60.0


def test_history_excludes_ungraded_modes(client):
    _record_session(client, "converse", reviewed=5, correct=5)
    assert client.get("/api/study/history").json() == []


def test_history_is_user_scoped(client):
    _record_session(client, "flashcard_jp", reviewed=4, correct=2)
    assert client.get("/api/study/history", headers={"X-User-ID": "other"}).json() == []


# ---- Cloze (no AI call) ------------------------------------------------------

CLOZE_EXAMPLES = '[{"japanese": "環境が変わりました。", "english": "The environment changed."}]'


def test_cloze_question_blanks_the_word(client):
    item = client.post("/api/items/", json=_make_item(
        japanese="環境", reading="かんきょう", example_sentences=CLOZE_EXAMPLES,
    )).json()

    r = client.post(f"/api/generate/question?item_id={item['id']}&mode=cloze")
    assert r.status_code == 200
    q = r.json()
    assert q["type"] == "cloze"
    assert "環境" not in q["prompt"]
    assert q["answer"] == "環境"
    assert "かんきょう" in q["accepted"]
    assert q["translation"] == "The environment changed."


def test_cloze_422s_when_the_word_is_absent_from_every_example(client):
    item = client.post("/api/items/", json=_make_item(
        japanese="環境", example_sentences='[{"japanese": "無関係な文。", "english": "Unrelated."}]',
    )).json()
    r = client.post(f"/api/generate/question?item_id={item['id']}&mode=cloze")
    assert r.status_code == 422


def test_cloze_422s_without_examples(client):
    item = client.post("/api/items/", json=_make_item(japanese="環境")).json()
    assert client.post(f"/api/generate/question?item_id={item['id']}&mode=cloze").status_code == 422


def test_cloze_404s_across_users(client):
    item = client.post("/api/items/", json=_make_item(example_sentences=CLOZE_EXAMPLES)).json()
    r = client.post(
        f"/api/generate/question?item_id={item['id']}&mode=cloze", headers={"X-User-ID": "other"}
    )
    assert r.status_code == 404


# ---- require_item dependency ------------------------------------------------
# The shared dependency binds item_id from the path on /items/{item_id} and from
# the query string on /generate/*. That resolution is implicit, so pin it here —
# these 404s happen in the dependency, before any AI call, so no API key needed.

def test_generate_question_404s_for_unknown_item(client):
    r = client.post("/api/generate/question?item_id=99999&mode=fill_blank")
    assert r.status_code == 404


def test_generate_question_404s_across_users(client):
    item = client.post("/api/items/", json=_make_item(),
                       headers={"X-User-ID": "alice"}).json()
    r = client.post(
        f"/api/generate/question?item_id={item['id']}&mode=fill_blank",
        headers={"X-User-ID": "bob"},
    )
    assert r.status_code == 404


def test_generate_example_sentence_404s_for_unknown_item(client):
    assert client.post("/api/generate/example-sentence?item_id=99999").status_code == 404


def test_generate_question_requires_item_id(client):
    """A missing item_id is a 422 from validation, not a 500 from the dependency."""
    assert client.post("/api/generate/question?mode=fill_blank").status_code == 422


def test_item_id_is_documented_as_a_query_param(client):
    spec = client.get("/openapi.json").json()
    params = spec["paths"]["/api/generate/question"]["post"]["parameters"]
    item_id = next(p for p in params if p["name"] == "item_id")
    assert item_id["in"] == "query"
    assert item_id["required"] is True


def test_review_invalid_rating_rejected(client):
    item = client.post("/api/items/", json=_make_item()).json()
    r = client.post("/api/study/review", json={"item_id": item["id"], "rating": "excellent"})
    assert r.status_code == 422


# ---- Tag filtering ----------------------------------------------------------

def test_items_filter_by_tag(client):
    client.post("/api/items/", json=_make_item(japanese="食べる", meaning="to eat", tags=["verb"]))
    client.post("/api/items/", json=_make_item(japanese="速い", meaning="fast", tags=["adjective"]))
    r = client.get("/api/items/?tag=verb")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["japanese"] == "食べる"


# ---- Multi-user isolation ---------------------------------------------------

def test_user_isolation_items(client):
    # alice creates an item
    client.post("/api/items/", json=_make_item(japanese="猫", meaning="cat"),
                headers={"X-User-ID": "alice"})

    # bob sees nothing
    bob_items = client.get("/api/items/", headers={"X-User-ID": "bob"}).json()
    assert bob_items == []

    # alice sees her item
    alice_items = client.get("/api/items/", headers={"X-User-ID": "alice"}).json()
    assert len(alice_items) == 1
    assert alice_items[0]["japanese"] == "猫"


def test_user_isolation_cross_access_404(client):
    # alice creates an item
    item = client.post("/api/items/", json=_make_item(),
                       headers={"X-User-ID": "alice"}).json()

    # bob cannot read, update, or delete it
    assert client.get(f"/api/items/{item['id']}", headers={"X-User-ID": "bob"}).status_code == 404
    assert client.put(f"/api/items/{item['id']}", json={"meaning": "x"},
                      headers={"X-User-ID": "bob"}).status_code == 404
    assert client.delete(f"/api/items/{item['id']}",
                         headers={"X-User-ID": "bob"}).status_code == 404


def test_user_isolation_settings(client):
    # alice sets N1
    client.put("/api/settings/", json={"jlpt_level": "N1"}, headers={"X-User-ID": "alice"})

    # bob still sees the default N3
    assert client.get("/api/settings/", headers={"X-User-ID": "bob"}).json() == {"jlpt_level": "N3"}

    # alice still sees N1
    assert client.get("/api/settings/", headers={"X-User-ID": "alice"}).json() == {"jlpt_level": "N1"}


def test_user_isolation_dashboard(client):
    client.post("/api/items/", json=_make_item(), headers={"X-User-ID": "alice"})

    alice_dash = client.get("/api/study/dashboard", headers={"X-User-ID": "alice"}).json()
    bob_dash = client.get("/api/study/dashboard", headers={"X-User-ID": "bob"}).json()

    assert alice_dash["total_items"] == 1
    assert bob_dash["total_items"] == 0
