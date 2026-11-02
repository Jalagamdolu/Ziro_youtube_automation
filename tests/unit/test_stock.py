"""Stock photos (D-33, D-34): providers by key, code filters, query-hash cache, license rows,
reviewer swaps and the credit. HTTP is mocked with respx; nothing is called."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.adapters import stock


def hit(i: int, tags: str, ai: bool = False) -> dict:
    return {"id": i, "pageURL": f"https://pixabay.com/photos/p-{i}/", "tags": tags,
            "isAiGenerated": ai, "largeImageURL": f"https://pixabay.com/get/{i}_1280.jpg",
            "webformatURL": f"https://pixabay.com/get/{i}_640.jpg"}


class Fake:
    name = "pixabay"

    def search(self, query: str) -> list[stock.Photo]:
        return [stock.Photo("pixabay", f"{query[:3]}{i}", f"https://pixabay.com/photos/{i}/",
                            "u", "p", "desk, notebook", "Pixabay License", "https://lic")
                for i in range(3)]


@pytest.fixture
def runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    return tmp_path


@respx.mock
def test_pixabay_photos_drop_ai_faces_minors_and_brands() -> None:
    respx.get(stock.PIXABAY).mock(return_value=httpx.Response(200, json={"hits": [
        hit(1, "desk, notebook, hands, laptop"),
        hit(2, "office, abstract", ai=True),
        hit(3, "woman, portrait, smiling"),
        hit(4, "classroom, children, pupils"),
        hit(5, "phone, iphone, screen")]}))
    photos = stock.PixabayStock("key").search("student notebook")
    assert [p.id for p in photos] == ["1"]
    params = respx.calls[0].request.url.params
    assert (params["image_type"], params["orientation"], params["safesearch"]) == (
        "photo", "vertical", "true")


def test_providers_follow_keys_and_a_missing_pexels_key_is_silent(monkeypatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("PIXABAY_API_KEY", "p")
    assert [p.name for p in stock.get()] == ["pixabay"]
    monkeypatch.setenv("PEXELS_API_KEY", "x")
    assert [p.name for p in stock.get()] == ["pixabay", "pexels"]
    monkeypatch.delenv("PIXABAY_API_KEY")
    monkeypatch.delenv("PEXELS_API_KEY")
    assert stock.get() == []  # no photos at all: solid backgrounds


@respx.mock
def test_pexels_filters_by_alt_text() -> None:
    respx.get(stock.PEXELS).mock(return_value=httpx.Response(200, json={"photos": [
        {"id": 7, "url": "https://www.pexels.com/photo/7/", "alt": "Server room cables",
         "src": {"portrait": "https://images.pexels.com/7p.jpg", "medium": "m"}},
        {"id": 8, "url": "https://www.pexels.com/photo/8/", "alt": "Smiling woman portrait",
         "src": {"portrait": "https://images.pexels.com/8p.jpg", "medium": "m"}}]}))
    assert [p.id for p in stock.PexelsStock("key").search("server")] == ["7"]


@respx.mock
def test_candidates_are_cached_by_query_hash(runs) -> None:
    route = respx.get(stock.PIXABAY).mock(return_value=httpx.Response(200, json={
        "hits": [hit(i, "desk, notebook") for i in range(6)]}))
    provider = [stock.PixabayStock("key")]
    photos, searches = stock.candidates(provider, "student notebook")
    assert (len(photos), searches) == (stock.CANDIDATES, 1)
    assert stock.candidates(provider, "student notebook")[1] == 0
    assert route.call_count == 1


def test_storyboard_phrases_come_from_the_model_or_the_scene_words() -> None:
    from app.nodes.storyboarding import photo_query

    flow = {"visual_type": "flow", "on_screen": 'flow - "Search" to "Read"',
            "text": "It searches, reads and writes the calendar entries."}
    assert photo_query(flow, "Hands typing on Apple MacBook keyboard") == \
        "hands typing on keyboard"  # brands stripped from the model's phrase
    assert photo_query(flow, "") == "search read searches"  # code fallback
    assert photo_query({"visual_type": "end_card", "on_screen": "", "text": ""}, "x") is None


def test_photos_take_the_reviewers_swap_and_record_licenses(client, monkeypatch, tmp_path
                                                            ) -> None:
    from conftest import create

    from app.adapters import storage
    from app.core import db
    from app.core.models import AssetLicense, Cost
    from app.nodes.rendering import PHOTO_CHOICES, photos, stock_checks

    monkeypatch.setattr(stock, "get", lambda: [Fake()])
    monkeypatch.setattr(stock, "download", lambda photo: photo.id.encode())
    project_id = create(client)
    storage.get().write(PHOTO_CHOICES.format(project_id), b'{"S2": 2}')
    scenes = [{"id": "S1", "photo_query": "exam timetable"},
              {"id": "S2", "photo_query": "server room"},
              {"id": "S3", "photo_query": None}]
    footage = photos(project_id, scenes, tmp_path)

    assert [s.get("photo") for s in scenes] == ["photo_S1.jpg", "photo_S2.jpg", None]
    assert (tmp_path / "photo_S2.jpg").read_bytes() == b"ser2"  # the reviewer's candidate
    assert [r["chosen"] for r in footage["scenes"]] == [0, 2]
    assert footage["credit"] == "Images: Pixabay"
    report = stock_checks(project_id, footage)
    assert report["all_licensed"] and report["no_faces_minors_or_brands"]
    with db.session() as s:
        rows = s.query(AssetLicense).filter_by(project_id=project_id).all()
        assert sorted(r.query for r in rows) == ["exam timetable", "server room"]
        assert s.query(Cost).filter_by(project_id=project_id,
                                       provider="pixabay-search").one().units == 2


def test_swapping_a_photo_at_qa_review_rerenders_with_a_recorded_note(client, monkeypatch
                                                                      ) -> None:
    from conftest import run_to_qa_review, status

    import app.nodes as nodes
    from app.adapters import storage
    from app.nodes import stubs
    from app.nodes.rendering import PHOTO_CHOICES

    renders: list[str | None] = []
    candidate = {"page_url": "https://pixabay.com/photos/1/", "preview_url": "https://p/1.jpg",
                 "tags": "desk"}

    def rendering_with_photos(ctx):  # type: ignore[no-untyped-def]
        renders.append(ctx.notes)
        return stubs.rendering(ctx) | {
            "stock.json": json.dumps({"credit": "Images: Pixabay", "scenes": [
                {"scene": "S1", "query": "desk", "chosen": 0,
                 "candidates": [candidate, candidate | {"preview_url": "https://p/2.jpg"}]}]}),
            "qa_report.json": json.dumps({"stock": {"credit": "Images: Pixabay"}})}

    monkeypatch.setitem(nodes.FUNCS, "rendering", rendering_with_photos)
    project_id = run_to_qa_review(client)
    page = client.get(f"/ui/projects/{project_id}").text
    assert "https://p/2.jpg" in page and "Use this photo" in page

    client.post(f"/ui/projects/{project_id}/photo",
                data={"scene": "S1", "index": "1", "reviewer": "Dolender"})
    run = status(client, project_id)
    assert run["status"] == "qa_review" and len(renders) == 2
    assert renders[1] == "Photo swap by Dolender: scene S1 uses candidate 2."
    assert json.loads(storage.get().read(PHOTO_CHOICES.format(project_id))) == {"S1": 1}


def test_mock_publish_credits_the_images(client, monkeypatch) -> None:
    from conftest import DISCLOSURE, approve, run_to_qa_review, status

    import app.nodes as nodes
    from app.adapters import storage
    from app.nodes import stubs

    def rendering_with_photos(ctx):  # type: ignore[no-untyped-def]
        return stubs.rendering(ctx) | {"stock.json": json.dumps({"credit": "Images: Pixabay"})}

    monkeypatch.setitem(nodes.FUNCS, "rendering", rendering_with_photos)
    project_id = run_to_qa_review(client)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    receipt = next(a for a in status(client, project_id)["artifacts"]
                   if a["type"] == "publish_receipt.json")
    description = json.loads(storage.get().read(receipt["storage_path"]))["request"]["snippet"][
        "description"]
    assert description.endswith("\n\nImages: Pixabay")
