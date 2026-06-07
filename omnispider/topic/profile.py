from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TopicProfile:
    """Parsed topic query for entity-centric crawling."""

    raw: str
    terms: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    primary: str = ""

    @classmethod
    def parse(cls, query: str) -> TopicProfile:
        raw = query.strip()
        if not raw:
            raise ValueError("Topic query cannot be empty")

        stopwords = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "about",
        }
        terms = [
            t.lower()
            for t in re.findall(r"[a-zA-Z0-9_@.-]+", raw)
            if len(t) > 1 and t.lower() not in stopwords
        ]
        terms = list(dict.fromkeys(terms))

        phrases: list[str] = []
        words = raw.split()
        for size in (4, 3, 2):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i : i + size]).strip()
                if len(phrase) > 4:
                    phrases.append(phrase.lower())
        phrases = list(dict.fromkeys(phrases))

        primary = phrases[0] if phrases else (terms[0] if terms else raw.lower())

        return cls(raw=raw, terms=terms, phrases=phrases, primary=primary)

    def term_set(self) -> set[str]:
        return set(self.terms)

    def slug_variants(self) -> list[str]:
        """Generate URL slug variants (e.g. asher-newton, asher_shepherd)."""
        slugs: list[str] = []
        if len(self.terms) >= 2:
            slugs.append("-".join(self.terms[:2]))
            slugs.append("-".join(self.terms[:3]))
            slugs.append("_".join(self.terms[:2]))
        for term in self.terms:
            if len(term) > 3:
                slugs.append(term)
        return list(dict.fromkeys(slugs))
