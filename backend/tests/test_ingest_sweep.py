"""sweep.py — uncovered mentions and uncitable fragments become sweep flags (§5.6, §11.3)."""

from app.ingest.chunk import ChunkSpec
from app.ingest.sweep import reconcile
from app.schemas.ingestion import SweepResult

TEXT = ("Admins can export the audit log as CSV. We might offer a mobile app someday. "
        "Dark mode is nice.")
CHUNKS = [
    ChunkSpec(chunk_id="c0", ordinal=0, section_path=["Ideas"], char_start=0,
              char_end=len(TEXT), text=TEXT),
    ChunkSpec(chunk_id="c1", ordinal=1, section_path=["Empty"], char_start=len(TEXT) + 2,
              char_end=len(TEXT) + 12, text="Nothing here"),
]
FEATURE = {
    "name": "Audit log export",
    "source_refs": [{"doc_id": "d1", "chunk_id": "c0", "char_start": 0, "char_end": 39,
                     "snippet": TEXT[:39]}],
}
PAYLOAD_KEYS = {"feature_name", "description", "reason", "confidence", "source_ref"}


def _run(sweeps, unlocated=()):
    return reconcile(chunks=CHUNKS, sweeps=sweeps, features=[FEATURE], fragments=[],
                     unlocated=list(unlocated), document_id="d1", doc_type="upload")


def test_covered_mentions_are_not_flagged_and_uncovered_are():
    sweeps = {0: SweepResult.model_validate({"mentions": [
        {"name": "CSV export of audit log", "snippet": "export the audit log as CSV",
         "confidence": 0.9},
        {"name": "Mobile app", "snippet": "We might offer a mobile app someday.",
         "confidence": 0.4},
        {"name": "Dark mode", "snippet": "Dark mode is lovely.", "confidence": 0.3},
    ]}), 1: SweepResult()}
    flags, zero = _run(sweeps)
    assert [f["feature_name"] for f in flags] == ["Mobile app", "Dark mode"]
    assert all(set(f) == PAYLOAD_KEYS for f in flags)
    mobile, dark = flags
    assert mobile["source_ref"]["snippet"] == "We might offer a mobile app someday."
    assert "located" not in mobile["source_ref"]
    # quote not verbatim → still cited (whole chunk), marked unlocated — never dropped
    assert dark["source_ref"]["located"] is False
    assert dark["source_ref"]["snippet"] == TEXT[:300]
    assert zero == [1]  # the empty chunk contributed nothing → spot-check list


def test_unlocated_fragments_become_flags():
    flags, _ = _run({0: SweepResult()}, unlocated=[{
        "feature_name": "Password rotation", "description": "Passwords rotate.",
        "snippet": "Passwords must rotate every 90 days.", "confidence": 0.5,
        "chunk_ordinal": 0,
    }])
    assert flags == [{
        "feature_name": "Password rotation", "description": "Passwords rotate.",
        "reason": "no_locatable_source", "confidence": 0.5,
        "source_ref": {**flags[0]["source_ref"], "located": False},
    }]
    assert flags[0]["source_ref"]["chunk_id"] == "c0"
