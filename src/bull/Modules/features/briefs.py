"""Feature briefs in `docs/features/<slug>.md`."""

from __future__ import annotations

from bull.Modules.features.Contracts import Idea
from bull.Modules.foundation.Contracts import AppLayout, Files


def brief_path(app: AppLayout, slug: str) -> str:
    """The brief's path relative to the app root, as stored in `BacklogItem.brief`."""
    return (app.features_dir / f"{slug}.md").relative_to(app.root).as_posix()


def render_brief(idea: Idea) -> str:
    """The brief template: title heading, then `Idea` (holding the description),
    `Discussion notes` and `Agreed scope`."""
    parts = [f"# {idea.title}", "## Idea"]
    description = idea.description.strip()
    if description:
        parts.append(description)
    parts += ["## Discussion notes", "## Agreed scope"]
    return "\n\n".join(parts) + "\n"


def write_brief(app: AppLayout, files: Files, slug: str, idea: Idea) -> str:
    """Writes `docs/features/<slug>.md` from the template; returns its relative path."""
    files.write_atomic(app.features_dir / f"{slug}.md", render_brief(idea))
    return brief_path(app, slug)
