"""Loading and validating the user's preferences file."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREFERENCES = ROOT / "preferences.yaml"
DEFAULT_KB_DIR = ROOT / "knowledge_base"
DEFAULT_OUTPUT_DIR = ROOT / "output"


@dataclass
class SearchPrefs:
    keywords: list[str]
    locations: list[str] = field(default_factory=lambda: [""])
    posted_within_days: int = 7
    workplace: list[str] = field(default_factory=list)
    experience_levels: list[str] = field(default_factory=list)
    job_types: list[str] = field(default_factory=list)
    max_results_per_query: int = 25
    request_delay_seconds: float = 2.5


@dataclass
class FilterPrefs:
    exclude_companies: list[str] = field(default_factory=list)
    exclude_title_keywords: list[str] = field(default_factory=list)
    required_keywords: list[str] = field(default_factory=list)


@dataclass
class RankingPrefs:
    min_score: int = 65
    priorities: str = ""


@dataclass
class DocumentPrefs:
    top_n: int = 5
    language: str = "English"
    cv_guidance: str = ""
    cover_letter_guidance: str = ""


@dataclass
class ClaudePrefs:
    model: str = "claude-opus-5-5"
    scoring_effort: str = "low"
    writing_effort: str = "high"


@dataclass
class Preferences:
    search: SearchPrefs
    filters: FilterPrefs
    ranking: RankingPrefs
    documents: DocumentPrefs
    claude: ClaudePrefs
    raw_yaml: str  # verbatim file contents, handed to Claude as context

    @classmethod
    def load(cls, path: Path = DEFAULT_PREFERENCES) -> "Preferences":
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Copy preferences.example.yaml to preferences.yaml and edit it."
            )
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        search = data.get("search") or {}
        if not search.get("keywords"):
            raise ValueError("preferences: search.keywords must list at least one search term")
        if not search.get("locations"):
            search["locations"] = [""]
        return cls(
            search=SearchPrefs(**search),
            filters=FilterPrefs(**(data.get("filters") or {})),
            ranking=RankingPrefs(**(data.get("ranking") or {})),
            documents=DocumentPrefs(**(data.get("documents") or {})),
            claude=ClaudePrefs(**(data.get("claude") or {})),
            raw_yaml=text,
        )
