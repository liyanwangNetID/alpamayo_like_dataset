from pathlib import Path


def test_step9_handoff_is_canonical_and_complete():
    workspace = Path(__file__).resolve().parents[3]
    handoff = workspace / "docs" / "AI_DATASET_DEVELOPMENT_HANDOFF.md"
    step9_readme = workspace / "dataset_tools" / "step9" / "README.md"

    assert handoff.is_file()
    assert not step9_readme.exists()

    text = handoff.read_text(encoding="utf-8")
    normalized = " ".join(text.casefold().split())

    assert "step 9: human-readable reasoning" in normalized

    assert "default" in normalized
    assert "training" in normalized
    assert "excluded" in normalized

    assert "experimental" in normalized
    assert "auxiliary" in normalized
