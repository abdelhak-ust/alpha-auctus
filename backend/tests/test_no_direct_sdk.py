"""Guard: no module outside agents/llm.py imports google.genai or builds a chat model."""

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

FORBIDDEN_IMPORTS = (
    "from google import genai",
    "from google.genai",
    "import google.genai",
    "ChatGoogleGenerativeAI(",
    "ChatVertexAI(",
    "from langchain_google_genai",
    "from langchain_google_vertexai",
)


def test_no_direct_sdk_or_chat_model_outside_llm():
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        if path.name.startswith("._"):
            continue
        if path.name == "llm.py" and path.parent.name == "agents":
            continue
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_IMPORTS:
            if needle in text:
                offenders.append(f"{path.relative_to(APP)}: {needle}")
    assert offenders == []


def test_llm_factory_exists():
    text = (APP / "agents" / "llm.py").read_text(encoding="utf-8")
    assert "def get_chat_model" in text
    assert "VertexNotConfigured" in text
