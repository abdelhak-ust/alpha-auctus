"""Feature Extractor (pass 1) and Feature Merger — structured-output agents."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_chat_model
from app.agents.prompts import EXTRACTOR, MERGER
from app.schemas.mvp import ExtractedFeature, ExtractedFeatures, MergedFeatures


def _running_list(features: list[ExtractedFeature]) -> str:
    if not features:
        return "(none yet)"
    return "\n".join(f"- {f.name}: {f.summary}" for f in features)


async def extract_features(
    chunk_text: str, running: list[ExtractedFeature]
) -> list[ExtractedFeature]:
    """Pass 1: new features in this chunk only, never repeats."""
    model = get_chat_model().with_structured_output(ExtractedFeatures)
    result = await model.ainvoke(
        [
            SystemMessage(content=EXTRACTOR),
            HumanMessage(
                content=(
                    f"Features found so far:\n{_running_list(running)}\n\n"
                    f"Chunk:\n{chunk_text}"
                )
            ),
        ]
    )
    if isinstance(result, ExtractedFeatures):
        return result.features
    if isinstance(result, dict):
        return ExtractedFeatures.model_validate(result).features
    return []


async def merge_features(features: list[ExtractedFeature]) -> list[ExtractedFeature]:
    """Merge near-duplicates across chunks, keeping every quote."""
    if len(features) <= 1:
        return features
    model = get_chat_model().with_structured_output(MergedFeatures)
    payload = "\n\n".join(
        f"## {f.name}\n{f.summary}\nQuotes:\n" + "\n".join(f"- {q}" for q in f.source_quotes)
        for f in features
    )
    result = await model.ainvoke(
        [
            SystemMessage(content=MERGER),
            HumanMessage(content=f"Merge these extracted features:\n\n{payload}"),
        ]
    )
    if isinstance(result, MergedFeatures):
        return result.features
    if isinstance(result, dict):
        return MergedFeatures.model_validate(result).features
    return features
