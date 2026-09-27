"""Extractor / Merger: structured-output agents via the fake chat model."""

from app.agents.extractor import extract_features, merge_features
from app.agents.llm import set_chat_model_override
from app.schemas.mvp import ExtractedFeature, ExtractedFeatures, MergedFeatures
from tests.fakes import FakeChatModel


async def test_extractor_returns_new_features_only(monkeypatch):
    fake = FakeChatModel(
        script=[
            ExtractedFeatures(
                features=[
                    ExtractedFeature(
                        name="Email sign-in",
                        summary="Users sign in with email.",
                        source_quotes=["Users can sign in with their work email."],
                    )
                ]
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        got = await extract_features("Users can sign in with their work email.", [])
        assert [f.name for f in got] == ["Email sign-in"]
    finally:
        set_chat_model_override(None)


async def test_merger_dedupes_across_chunks():
    fake = FakeChatModel(
        script=[
            MergedFeatures(
                features=[
                    ExtractedFeature(
                        name="Email sign-in",
                        summary="Canonical sign-in.",
                        source_quotes=["quote a", "quote b"],
                    )
                ]
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        merged = await merge_features(
            [
                ExtractedFeature(name="Email sign-in", summary="A", source_quotes=["quote a"]),
                ExtractedFeature(name="Sign in with email", summary="B", source_quotes=["quote b"]),
            ]
        )
        assert len(merged) == 1
        assert merged[0].source_quotes == ["quote a", "quote b"]
    finally:
        set_chat_model_override(None)


async def test_merger_skips_single_feature():
    one = [ExtractedFeature(name="Only", summary="one", source_quotes=["x" * 10])]
    assert await merge_features(one) == one
