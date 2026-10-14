#!/usr/bin/env python3
"""Validate the static site's SEO metadata, structured data, and local links."""

from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
SITE_ORIGIN = "https://topdogtourandtaxi.com/"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.descriptions = 0
        self.h1s = 0
        self.ids: list[str] = []
        self.local_refs: list[str] = []
        self.robots = 0
        self.titles = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title":
            self.titles += 1
        elif tag == "h1":
            self.h1s += 1
        elif tag == "meta" and attributes.get("name") == "description":
            self.descriptions += 1
        elif tag == "meta" and attributes.get("name") == "robots":
            self.robots += 1
        elif tag == "link" and attributes.get("rel") == "canonical":
            href = attributes.get("href")
            if href:
                self.canonicals.append(href)

        element_id = attributes.get("id")
        if element_id:
            self.ids.append(element_id)

        for attribute in ("href", "src"):
            reference = attributes.get(attribute)
            if reference and not reference.startswith(
                ("#", "http://", "https://", "tel:", "mailto:", "sms:", "data:")
            ):
                self.local_refs.append(reference.split("#", 1)[0].split("?", 1)[0])


def validate_page(path: Path) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(source)

    expected_counts = {
        "title": (parser.titles, 1),
        "meta description": (parser.descriptions, 1),
        "robots meta": (parser.robots, 1),
        "canonical": (len(parser.canonicals), 1),
        "H1": (parser.h1s, 1),
    }
    for label, (actual, expected) in expected_counts.items():
        if actual != expected:
            errors.append(f"{path.name}: expected {expected} {label}, found {actual}")

    if parser.canonicals and not parser.canonicals[0].startswith(SITE_ORIGIN):
        errors.append(f"{path.name}: canonical must use {SITE_ORIGIN}")

    duplicates = [element_id for element_id, count in Counter(parser.ids).items() if count > 1]
    if duplicates:
        errors.append(f"{path.name}: duplicate IDs: {', '.join(duplicates)}")

    for reference in parser.local_refs:
        if reference and not (ROOT / reference).exists():
            errors.append(f"{path.name}: missing local target {reference}")

    for block in re.findall(
        r'<script\s+type=["\']application/ld\+json["\']>(.*?)</script>', source, re.DOTALL
    ):
        try:
            json.loads(block)
        except json.JSONDecodeError as error:
            errors.append(f"{path.name}: invalid JSON-LD: {error}")

    if "<<<<<<<" in source or ">>>>>>>" in source:
        errors.append(f"{path.name}: unresolved merge-conflict marker")

    return errors


def validate_sitemap() -> list[str]:
    errors: list[str] = []
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    root = ET.parse(ROOT / "sitemap.xml").getroot()
    locations = [item.text for item in root.findall(f"{namespace}url/{namespace}loc")]

    if len(locations) != len(set(locations)):
        errors.append("sitemap.xml: duplicate URLs")

    for location in locations:
        if not location or not location.startswith(SITE_ORIGIN):
            errors.append(f"sitemap.xml: invalid canonical URL {location!r}")
            continue
        relative_path = location.removeprefix(SITE_ORIGIN) or "index.html"
        if not (ROOT / relative_path).is_file():
            errors.append(f"sitemap.xml: missing page {relative_path}")

    return errors


def main() -> int:
    errors: list[str] = []
    for page in sorted(ROOT.glob("*.html")):
        errors.extend(validate_page(page))
    errors.extend(validate_sitemap())

    if errors:
        print("Site validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Site validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
