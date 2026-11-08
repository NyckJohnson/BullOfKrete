"""Tests for `bull.Modules.features.briefs`: the feature brief files in `docs/features/`.

The briefs file has no public contract of its own, so these tests drive it through
`LiveBacklog.add`, the behavior the spec states: "writes `docs/features/<slug>.md` from the
brief template".
"""

from __future__ import annotations

from bull.Modules.features.backlog import LiveBacklog
from bull.Modules.features.Contracts import Idea
from bull.Modules.features.mocks import MockIdeaReader
from bull.Modules.foundation.mocks import MockClock, MockFiles, sample_layout

LAYOUT = sample_layout()


def _backlog() -> tuple[LiveBacklog, MockFiles]:
    files = MockFiles()
    return LiveBacklog(LAYOUT, files, MockClock(), MockIdeaReader()), files


def test_brief_is_written_at_docs_features_slug_md() -> None:
    backlog, files = _backlog()
    item = backlog.add(Idea("Reset button", "Sets the counter to zero."))
    path = LAYOUT.features_dir / "reset-button.md"
    assert path in files.texts
    assert item.brief == "docs/features/reset-button.md"


def test_brief_starts_with_the_title_heading() -> None:
    backlog, files = _backlog()
    backlog.add(Idea("Reset button", "Sets the counter to zero."))
    text = files.texts[LAYOUT.features_dir / "reset-button.md"]
    assert text.splitlines()[0] == "# Reset button"


def test_brief_has_the_three_sections_in_template_order() -> None:
    backlog, files = _backlog()
    backlog.add(Idea("Reset button", "Sets the counter to zero."))
    text = files.texts[LAYOUT.features_dir / "reset-button.md"]
    lines = text.splitlines()
    heads = [line for line in lines if line.startswith("#")]
    assert heads == [
        "# Reset button",
        "## Idea",
        "## Discussion notes",
        "## Agreed scope",
    ]


def test_brief_idea_section_holds_the_description() -> None:
    backlog, files = _backlog()
    backlog.add(Idea("Reset button", "Sets the counter to zero."))
    text = files.texts[LAYOUT.features_dir / "reset-button.md"]
    idea = text.split("## Idea")[1].split("## Discussion notes")[0]
    assert "Sets the counter to zero." in idea
    assert "Sets the counter to zero." not in text.split("## Discussion notes")[1]


def test_brief_with_empty_description_still_has_all_sections() -> None:
    backlog, files = _backlog()
    backlog.add(Idea("Export", ""))
    text = files.texts[LAYOUT.features_dir / "export.md"]
    assert "## Idea" in text
    assert "## Discussion notes" in text
    assert "## Agreed scope" in text


def test_duplicate_title_gets_its_own_suffixed_brief_file() -> None:
    backlog, files = _backlog()
    backlog.add(Idea("Export", "csv"))
    second = backlog.add(Idea("Export", "json"))
    assert second.brief == "docs/features/export-2.md"
    assert (LAYOUT.features_dir / "export-2.md") in files.texts
    assert "csv" in files.texts[LAYOUT.features_dir / "export.md"]
    assert "json" in files.texts[LAYOUT.features_dir / "export-2.md"]


def test_dropping_an_item_keeps_its_brief_file() -> None:
    backlog, files = _backlog()
    backlog.add(Idea("Export", "csv"))
    backlog.drop("export")
    assert (LAYOUT.features_dir / "export.md") in files.texts
