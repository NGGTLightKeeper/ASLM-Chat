# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


# Database root and validation
DB_DIR = Path(
    os.getenv("GUIDE_DB_DIR", str(Path(__file__).resolve().parent / "guide_tools_db"))
)
VALID_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VALID_KIND = {"pattern", "synergy", "pitfall", "example"}


# Data models

# Store one resolved guide entry
@dataclass(frozen=True)
class GuideEntry:
    name: str
    guide_path: Path
    source: str
    folder_path: Path | None = None


# Store one snippet record with normalized metadata
@dataclass(frozen=True)
class SnippetRecord:
    owner_guide: str
    path: Path
    title: str
    kind: str
    status: str
    verification: str
    related_tools: tuple[str, ...]
    body: str

    @property
    def slug(self) -> str:
        """Return the snippet filename stem."""

        return self.path.stem


# Store one recipe record with parsed frontmatter
@dataclass(frozen=True)
class RecipeRecord:
    owner_guide: str
    path: Path
    title: str
    domain: str
    trigger: str
    tools: tuple[str, ...]
    related_guides: tuple[str, ...]
    difficulty: str
    body: str

    @property
    def slug(self) -> str:
        """Return the recipe filename stem."""

        return self.path.stem


# Time and validation helpers

# Return the current UTC timestamp in stable ISO format
def _utc_now() -> str:
    """Return a compact UTC timestamp for snippet metadata."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _safe_segment(value: str, field_name: str) -> str:
    """Validate one guide or snippet path segment."""

    candidate = str(value).strip()
    if not candidate or not VALID_SEGMENT.fullmatch(candidate):
        raise ValueError(
            f"Invalid {field_name}: '{value}'. Use only letters, numbers, dots, underscores, and dashes."
        )
    return candidate

def _normalize_related_tools(value: object) -> tuple[str, ...]:
    """Normalize related_tools into a deduplicated tuple of safe segments."""

    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [item for item in value if isinstance(item, str)]
    else:
        raise ValueError("related_tools must be a string or a list of strings.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = _safe_segment(item, "related tool")
        if normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)

    return tuple(cleaned)


# Path helpers

# Keep resolved paths inside the configured database root
def _secure_path(path: Path) -> Path:
    """Resolve a path and ensure it stays inside the guide database."""

    resolved = path.resolve()
    root = DB_DIR.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Access denied: path escapes guide_tools_db.")
    return resolved

def _guide_dir(guide: str) -> Path:
    """Return the folder path for a guide."""

    guide_name = _safe_segment(guide, "guide")
    return _secure_path(DB_DIR / guide_name)

def _guide_file(guide: str) -> Path:
    """Return the guide.md path for a folder-based guide."""

    return _secure_path(_guide_dir(guide) / "guide.md")

def _legacy_guide_file(guide: str) -> Path:
    """Return the legacy flat Markdown guide path."""

    guide_name = _safe_segment(guide, "guide")
    return _secure_path(DB_DIR / f"{guide_name}.md")

def _snippets_dir(guide: str) -> Path:
    """Return the active snippets directory for a guide."""

    return _secure_path(_guide_dir(guide) / "snippets")

def _recipes_dir(guide: str) -> Path:
    """Return the recipes directory for a guide."""

    return _secure_path(_guide_dir(guide) / "recipes")

def _deprecated_dir(guide: str) -> Path:
    """Return the deprecated snippets directory for a guide."""

    return _secure_path(_guide_dir(guide) / "_deprecated")

def _snippet_path(guide: str, snippet: str, deprecated: bool = False) -> Path:
    """Return the Markdown path for one snippet."""

    slug = _safe_segment(str(snippet).removesuffix(".md"), "snippet")
    base = _deprecated_dir(guide) if deprecated else _snippets_dir(guide)
    return _secure_path(base / f"{slug}.md")

def _recipe_path(guide: str, recipe: str) -> Path:
    """Return the Markdown path for one recipe."""

    slug = _safe_segment(str(recipe).removesuffix(".md"), "recipe")
    return _secure_path(_recipes_dir(guide) / f"{slug}.md")


# Frontmatter helpers

# Split YAML frontmatter from the Markdown body
def _split_frontmatter(raw_text: str) -> tuple[dict, str]:
    """Split YAML frontmatter and return metadata plus body text."""

    if not raw_text.startswith("---"):
        return {}, raw_text

    lines = raw_text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, raw_text

    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            frontmatter = "".join(lines[1:idx])
            body = "".join(lines[idx + 1 :]).lstrip("\r\n")
            data = yaml.safe_load(frontmatter) or {}
            if not isinstance(data, dict):
                data = {}
            return data, body

    return {}, raw_text

def _dump_frontmatter(meta: dict, body: str) -> str:
    """Serialize metadata and body back into Markdown with YAML frontmatter."""

    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=False).strip()
    cleaned_body = body.rstrip() + "\n"
    return f"---\n{frontmatter}\n---\n\n{cleaned_body}"


# Snippet file IO

# Read one snippet into a normalized record
def _read_snippet_record(owner_guide: str, snippet_path: Path) -> SnippetRecord:
    """Read one snippet file and normalize its metadata."""

    raw_text = snippet_path.read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw_text)
    title = str(meta.get("title") or snippet_path.stem).strip()
    kind = str(meta.get("kind") or "pattern").strip()
    status = str(meta.get("status") or "active").strip().lower()
    verification = str(meta.get("verification") or "unverified").strip()
    related_tools = _normalize_related_tools(meta.get("related_tools", []))
    return SnippetRecord(
        owner_guide=owner_guide,
        path=snippet_path,
        title=title,
        kind=kind,
        status=status,
        verification=verification,
        related_tools=related_tools,
        body=body.strip(),
    )

def _read_snippet_file(path: Path) -> tuple[dict, str]:
    """Read a snippet file and require valid YAML frontmatter."""

    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    if not meta:
        raise ValueError(f"Snippet is missing YAML frontmatter: {path.name}")
    return meta, body.rstrip()

def _write_snippet_file(path: Path, meta: dict, body: str) -> None:
    """Write a snippet file with normalized frontmatter."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_frontmatter(meta, body), encoding="utf-8")


# Guide discovery

# List folder-based guides
def _iter_folder_guides() -> list[GuideEntry]:
    """Return all folder-based guides that contain guide.md."""

    if not DB_DIR.exists():
        return []

    guides: list[GuideEntry] = []
    for child in DB_DIR.iterdir():
        if not child.is_dir():
            continue

        guide_path = child / "guide.md"
        if guide_path.is_file():
            guides.append(
                GuideEntry(
                    name=child.name,
                    guide_path=guide_path,
                    source="folder",
                    folder_path=child,
                )
            )

    return guides

def _iter_flat_guides() -> list[GuideEntry]:
    """Return all legacy flat Markdown guides."""

    if not DB_DIR.exists():
        return []

    return [
        GuideEntry(name=path.stem, guide_path=path, source="flat", folder_path=None)
        for path in DB_DIR.glob("*.md")
    ]

def _get_guides() -> list[GuideEntry]:
    """Return all guides, preferring folder-based entries over flat duplicates."""

    by_name: dict[str, GuideEntry] = {}

    for guide in _iter_flat_guides():
        by_name[guide.name.lower()] = guide

    for guide in _iter_folder_guides():
        by_name[guide.name.lower()] = guide

    return sorted(by_name.values(), key=lambda item: item.name.lower())

def _resolve_guide(name_or_index: str | int) -> GuideEntry | None:
    """Resolve a guide by exact name, partial name, or numeric index."""

    guides = _get_guides()
    if not guides:
        return None

    query = str(name_or_index).strip()

    try:
        idx = int(query)
        if 1 <= idx <= len(guides):
            return guides[idx - 1]
        if 0 <= idx < len(guides):
            return guides[idx]
        return None
    except ValueError:
        pass

    normalized_query = query.lower().removesuffix(".md")

    for guide in guides:
        if guide.name.lower() == normalized_query:
            return guide

    matches = [guide for guide in guides if normalized_query in guide.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return min(matches, key=lambda guide: len(guide.name))
    return None

def _guide_exists(guide: str) -> bool:
    """Return whether a guide exists in folder or legacy flat form."""

    return _guide_file(guide).exists() or _legacy_guide_file(guide).exists()

def _ensure_guide_layout(guide: str) -> Path:
    """Ensure the folder layout exists for a guide, migrating legacy guide.md when needed."""

    guide_dir = _guide_dir(guide)
    guide_md = _guide_file(guide)
    legacy_file = _legacy_guide_file(guide)

    if not guide_md.exists():
        if legacy_file.exists():
            guide_dir.mkdir(parents=True, exist_ok=True)
            guide_md.write_text(legacy_file.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise ValueError(f"Guide not found: {guide}")

    _snippets_dir(guide).mkdir(parents=True, exist_ok=True)
    _deprecated_dir(guide).mkdir(parents=True, exist_ok=True)
    return guide_dir


# Snippet discovery

# Check whether a snippet exists in active or deprecated state
def _snippet_exists(guide: str, snippet: str) -> bool:
    """Return whether the snippet exists in active or deprecated storage."""

    return _snippet_path(guide, snippet).exists() or _snippet_path(guide, snippet, deprecated=True).exists()

def _get_local_snippets(guide: GuideEntry) -> list[SnippetRecord]:
    """Return all active local snippets for a guide."""

    if guide.folder_path is None:
        return []

    snippets_dir = guide.folder_path / "snippets"
    if not snippets_dir.exists():
        return []

    records: list[SnippetRecord] = []
    for snippet_path in sorted(snippets_dir.glob("*.md")):
        record = _read_snippet_record(guide.name, snippet_path)
        if record.status == "active":
            records.append(record)

    return records

def _get_external_synergy_snippets(target_guide: GuideEntry) -> list[SnippetRecord]:
    """Return active snippets from other guides that reference the target guide."""

    target_name = target_guide.name.lower()
    records: list[SnippetRecord] = []

    for guide in _get_guides():
        if guide.folder_path is None or guide.name.lower() == target_name:
            continue

        snippets_dir = guide.folder_path / "snippets"
        if not snippets_dir.exists():
            continue

        for snippet_path in sorted(snippets_dir.glob("*.md")):
            record = _read_snippet_record(guide.name, snippet_path)
            if record.status != "active":
                continue

            related = {item.lower() for item in record.related_tools}
            if target_name in related:
                records.append(record)

    return sorted(records, key=lambda item: (item.owner_guide.lower(), item.slug.lower()))


# Recipe discovery

def _read_recipe_record(owner_guide: str, recipe_path: Path) -> RecipeRecord:
    """Read one recipe file and normalize its metadata."""

    raw_text = recipe_path.read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw_text)
    title = str(meta.get("title") or recipe_path.stem).strip()
    domain = str(meta.get("domain") or "general").strip()
    trigger = str(meta.get("trigger") or "").strip()
    raw_tools = meta.get("tools", [])
    if isinstance(raw_tools, str):
        raw_tools = [raw_tools]
    tools = tuple(str(t).strip() for t in raw_tools if isinstance(t, str))
    raw_guides = meta.get("related_guides", [])
    if isinstance(raw_guides, str):
        raw_guides = [raw_guides]
    related_guides = tuple(str(g).strip() for g in raw_guides if isinstance(g, str))
    difficulty = str(meta.get("difficulty") or "medium").strip()
    return RecipeRecord(
        owner_guide=owner_guide,
        path=recipe_path,
        title=title,
        domain=domain,
        trigger=trigger,
        tools=tools,
        related_guides=related_guides,
        difficulty=difficulty,
        body=body.strip(),
    )


def _get_recipes(guide: GuideEntry) -> list[RecipeRecord]:
    """Return all recipes for a single guide."""

    if guide.folder_path is None:
        return []

    recipes_dir = guide.folder_path / "recipes"
    if not recipes_dir.exists():
        return []

    records: list[RecipeRecord] = []
    for recipe_path in sorted(recipes_dir.glob("*.md")):
        records.append(_read_recipe_record(guide.name, recipe_path))

    return records


def _get_all_recipes() -> list[RecipeRecord]:
    """Return all recipes across all guides."""

    records: list[RecipeRecord] = []
    for guide in _get_guides():
        records.extend(_get_recipes(guide))
    return sorted(records, key=lambda r: (r.owner_guide.lower(), r.slug.lower()))


def _search_recipes(query: str) -> list[RecipeRecord]:
    """Search recipes by matching query against title, domain, trigger, and tools."""

    query_lower = query.lower().strip()
    if not query_lower:
        return []

    terms = query_lower.split()
    results: list[RecipeRecord] = []

    for recipe in _get_all_recipes():
        searchable = " ".join([
            recipe.title.lower(),
            recipe.domain.lower(),
            recipe.trigger.lower(),
            " ".join(recipe.tools),
            " ".join(recipe.related_guides),
            recipe.owner_guide.lower(),
        ])
        if all(term in searchable for term in terms):
            results.append(recipe)

    return results


def _resolve_recipe(name_or_query: str) -> RecipeRecord | None:
    """Resolve a recipe by exact slug, partial name, or domain."""

    query = name_or_query.strip().lower().removesuffix(".md")
    if not query:
        return None

    all_recipes = _get_all_recipes()

    # Exact slug match
    for recipe in all_recipes:
        if recipe.slug.lower() == query:
            return recipe

    # Partial slug or title match
    matches = [r for r in all_recipes if query in r.slug.lower() or query in r.title.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return min(matches, key=lambda r: len(r.slug))

    # Domain match
    matches = [r for r in all_recipes if query in r.domain.lower()]
    if len(matches) == 1:
        return matches[0]

    return None


# Rendering helpers

# Render one snippet block for assembled guide output
def _render_snippet(record: SnippetRecord, include_source: bool) -> str:
    """Render one snippet for the assembled guide view."""

    meta_parts = [f"kind: {record.kind}", f"verification: {record.verification}"]
    if include_source:
        meta_parts.insert(0, f"source guide: {record.owner_guide}")
    if record.related_tools:
        meta_parts.append(f"related tools: {', '.join(record.related_tools)}")

    heading = f"### {record.title}"
    if include_source:
        heading = f"{heading} ({record.owner_guide})"

    body = record.body or "_No snippet body provided._"
    return f"{heading}\n\n_Metadata: {', '.join(meta_parts)}_\n\n{body}"

def _render_recipe_summary(recipe: RecipeRecord) -> str:
    """Render a short summary line for a recipe."""

    trigger_short = recipe.trigger[:80] + "..." if len(recipe.trigger) > 80 else recipe.trigger
    return f"- **{recipe.title}** ({recipe.slug}) -- {trigger_short}"


def _render_recipe_full(recipe: RecipeRecord) -> str:
    """Render a full recipe block for assembled guide output."""

    meta_parts = [
        f"domain: {recipe.domain}",
        f"difficulty: {recipe.difficulty}",
        f"tools: {', '.join(recipe.tools)}",
    ]
    directive = (
        "**Directive:** This recipe is a binding workflow instruction for matching tasks. "
        "Follow its workflow, stop conditions, and anti-patterns as written. "
        "Do not substitute your own workflow unless a higher-priority system or tool rule explicitly requires it."
    )
    heading = f"### {recipe.title}"
    body = recipe.body or "_No recipe body provided._"
    return f"{heading}\n\n{directive}\n\n_Metadata: {', '.join(meta_parts)}_\n\n{body}"


def _assemble_guide_content(guide: GuideEntry, mode: str = "core") -> str:
    """Assemble one guide with optional recipes and snippets.

    Modes:
        core          -- guide.md + recipe index (titles only) + snippets
        core+recipes  -- guide.md + full recipe content + snippets
        full          -- same as core+recipes (kept for compatibility)

    Snippets always appear in all modes -- they are the model's accumulated field notes
    and should always be visible.
    """

    guide_text = guide.guide_path.read_text(encoding="utf-8").strip()
    recipes = _get_recipes(guide)
    local_snippets = _get_local_snippets(guide)
    external_snippets = _get_external_synergy_snippets(guide)

    parts = [
        f"# Guide: {guide.name}",
        "=" * 60,
        "",
        guide_text,
    ]

    # Recipe section -- verbosity depends on mode
    if recipes:
        if mode == "core":
            parts.extend(["", "## Available Recipes", ""])
            parts.extend(_render_recipe_summary(r) for r in recipes)
            parts.append("")
            parts.append("Use get_recipe(name) to load a specific recipe workflow.")
        else:  # core+recipes or full
            parts.extend(["", "## Recipes", ""])
            parts.extend(_render_recipe_full(r) for r in recipes)

    # Snippets always shown -- accumulated field notes
    if local_snippets:
        parts.extend(["", "## Local Snippets", ""])
        parts.extend(_render_snippet(record, include_source=False) for record in local_snippets)

    if external_snippets:
        parts.extend(["", "## Related Synergy Snippets", ""])
        parts.extend(_render_snippet(record, include_source=True) for record in external_snippets)

    return "\n".join(part for part in parts if part is not None).strip() + "\n"


# Listing helpers

# List snippet metadata for one guide
def _list_snippet_records(guide: str, include_deprecated: bool) -> list[dict]:
    """Return serialized snippet metadata for one guide."""

    if not _guide_exists(guide):
        raise ValueError(f"Guide not found: {guide}")

    records: list[dict] = []

    # Read active snippets first.
    snippets_dir = _snippets_dir(guide)
    if snippets_dir.exists():
        for path in sorted(snippets_dir.glob("*.md")):
            meta, _body = _read_snippet_file(path)
            records.append(
                {
                    "guide": guide,
                    "slug": path.stem,
                    "path": str(path.relative_to(DB_DIR)),
                    "title": meta.get("title", path.stem),
                    "kind": meta.get("kind", "pattern"),
                    "status": meta.get("status", "active"),
                    "verification": meta.get("verification", "unverified"),
                    "related_tools": meta.get("related_tools", []),
                }
            )

    # Optionally append deprecated snippets from the shadow folder.
    if include_deprecated:
        deprecated_dir = _deprecated_dir(guide)
        if deprecated_dir.exists():
            for path in sorted(deprecated_dir.glob("*.md")):
                meta, _body = _read_snippet_file(path)
                records.append(
                    {
                        "guide": guide,
                        "slug": path.stem,
                        "path": str(path.relative_to(DB_DIR)),
                        "title": meta.get("title", path.stem),
                        "kind": meta.get("kind", "pattern"),
                        "status": meta.get("status", "deprecated"),
                        "verification": meta.get("verification", "unverified"),
                        "related_tools": meta.get("related_tools", []),
                        "deprecated_at": meta.get("deprecated_at"),
                    }
                )

    return records
