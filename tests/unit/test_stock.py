"""Stock footage (D-33): providers by key, code filters, query hash cache, license rows, credit.
HTTP is mocked with respx; nothing is called."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.adapters import stock


def pixabay_hit(i: int, tags: str, ai: bool = False, size: int = 2_000_000) -> dict:
    return {"id": i, "pageURL": f"https://pixabay.com/videos/clip-{i}/", "tags": tags,
            "duration": 12, "isAiGenerated": ai,
            "videos": {"medium": {"url": f"https://cdn.pixabay.com/{i}.mp4", "size": size}}}


@pytest.fixture
def runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    return tmp_path


@respx.mock
def test_pixabay_drops_ai_generated_people_brands_and_huge_files() -> None:
    respx.get(stock.PIXABAY).mock(return_value=httpx.Response(200, json={"hits": [
        pixabay_hit(1, "technology, abstract, network"),
        pixabay_hit(2, "abstract, particles", ai=True),
        pixabay_hit(3, "business, woman, laptop"),
        pixabay_hit(4, "phone, apple, screen"),
        pixabay_hit(5, "data, lines", size=90_000_000)]}))
    clips = stock.PixabayStock("key").search("abstract technology")
    assert [c.id for c in clips] == ["1"]
    assert clips[0].license == "Pixabay License"
    assert respx.calls[0].request.url.params["safesearch"] == "true"


def test_providers_follow_keys_and_a_missing_pexels_key_is_silent(monkeypatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("PIXABAY_API_KEY", "p")
    assert [p.name for p in stock.get()] == ["pixabay"]
    monkeypatch.setenv("PEXELS_API_KEY", "x")
    assert [p.name for p in stock.get()] == ["pixabay", "pexels"]
    monkeypatch.delenv("PIXABAY_API_KEY")
    monkeypatch.delenv("PEXELS_API_KEY")
    assert stock.get() == []  # no footage at all: solid backgrounds


def test_background_query_comes_from_the_topic_in_code() -> None:
    assert stock.background_query("What makes an AI agent different from a chatbot?") == \
        "agent chatbot technology"
    assert stock.background_query("Why is it so?") == stock.FALLBACK_QUERY


@respx.mock
def test_results_are_cached_by_query_hash_and_the_fallback_query_fills_gaps(runs) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        rich = request.url.params["q"] == stock.FALLBACK_QUERY
        hits = [pixabay_hit(i, "abstract, technology") for i in range(5 if rich else 1)]
        return httpx.Response(200, json={"hits": hits})

    route = respx.get(stock.PIXABAY).mock(side_effect=answer)
    provider = [stock.PixabayStock("key")]
    query, clips, searches = stock.find(provider, "agent chatbot technology", 3)
    assert (query, len(clips), searches) == (stock.FALLBACK_QUERY, 3, 2)
    assert stock.find(provider, "agent chatbot technology", 3)[2] == 0  # all from the cache
    assert route.call_count == 2


@respx.mock
def test_pexels_filters_by_page_slug() -> None:
    respx.get(stock.PEXELS).mock(return_value=httpx.Response(200, json={"videos": [
        {"id": 7, "url": "https://www.pexels.com/video/abstract-blue-lines-7/", "duration": 9,
         "video_files": [{"quality": "hd", "link": "https://videos.pexels.com/7.mp4"}]},
        {"id": 8, "url": "https://www.pexels.com/video/woman-typing-on-laptop-8/", "duration": 9,
         "video_files": [{"quality": "hd", "link": "https://videos.pexels.com/8.mp4"}]}]}))
    assert [c.id for c in stock.PexelsStock("key").search("abstract")] == ["7"]


def test_backgrounds_record_licenses_and_tint_every_scene_but_the_end_card(
        client, monkeypatch, tmp_path) -> None:
    from conftest import create

    from app.core import db
    from app.core.models import AssetLicense, Cost
    from app.nodes.rendering import backgrounds, stock_checks

    class Fake:
        name = "pixabay"

        def search(self, query: str) -> list[stock.Clip]:
            return [stock.Clip("pixabay", str(i), f"https://pixabay.com/videos/{i}/", "u", 8.0,
                               "abstract, network", "Pixabay License", "https://lic")
                    for i in range(3)]

    monkeypatch.setattr(stock, "get", lambda: [Fake()])
    monkeypatch.setattr(stock, "download", lambda clip: b"MP4")
    project_id = create(client)
    scenes = [{"visual_type": t} for t in ("title", "flow", "checklist", "chat_bubble",
                                           "end_card")]
    footage = backgrounds(project_id, "What makes an AI agent different?", scenes,
                                    tmp_path)

    assert [s.get("background") for s in scenes] == [
        "background_0.mp4", "background_1.mp4", "background_2.mp4", "background_0.mp4", None]
    assert (tmp_path / "background_2.mp4").read_bytes() == b"MP4"
    assert footage["credit"] == "Stock footage: Pixabay"
    report = stock_checks(project_id, footage)
    assert report["all_licensed"] and report["no_people_or_brand_tags"]
    with db.session() as s:
        rows = s.query(AssetLicense).filter_by(project_id=project_id).all()
        assert {(r.license, r.query) for r in rows} == {("Pixabay License",
                                                         "agent technology")}
        assert s.query(Cost).filter_by(project_id=project_id,
                                       provider="pixabay-search").count() == 1


def test_mock_publish_credits_the_footage(client, monkeypatch) -> None:
    from conftest import DISCLOSURE, approve, run_to_qa_review, status

    import app.nodes as nodes
    from app.nodes import stubs

    def rendering_with_footage(ctx):  # type: ignore[no-untyped-def]
        return stubs.rendering(ctx) | {"stock.json": json.dumps(
            {"credit": "Stock footage: Pixabay", "clips": []})}

    monkeypatch.setitem(nodes.FUNCS, "rendering", rendering_with_footage)
    project_id = run_to_qa_review(client)
    approve(client, project_id, ai_disclosure=DISCLOSURE)
    receipt = next(a for a in status(client, project_id)["artifacts"]
                   if a["type"] == "publish_receipt.json")
    from app.adapters import storage
    description = json.loads(storage.get().read(receipt["storage_path"]))["request"]["snippet"][
        "description"]
    assert description.endswith("\n\nStock footage: Pixabay")
