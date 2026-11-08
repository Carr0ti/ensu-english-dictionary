#!/usr/bin/env python3
"""Stream Kaikki/Wiktextract JSONL and build Ensu-friendly Markdown shards."""

from __future__ import annotations
import argparse
import datetime as dt
import gzip
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
USER_AGENT = "ensu-english-dictionary-builder/1.0 (GitHub Actions)"
DB_PATH = Path("build/dictionary.sqlite3")
OUT_DIR = Path("build/dictionary")
CHUNK_SIZE = 500

def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return ""

def list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            s = clean(item)
        elif isinstance(item, dict):
            s = clean(item.get("word") or item.get("name") or item.get("text"))
        else:
            s = ""
        if s and s not in result:
            result.append(s)
    return result

def is_form_entry(entry: dict) -> bool:
    # Wiktextract uses form_of for inflected forms; some records mark this in tags.
    if entry.get("form_of"):
        return True
    tags = set(entry.get("tags") or [])
    return bool(tags.intersection({"form-of", "form of"}))

def entry_to_markdown(entry: dict) -> str:
    word = clean(entry.get("word"))
    pos = clean(entry.get("pos")) or "Unspecified part of speech"
    blocks = [f"### {word}", f"**Part of speech:** {pos}"]

    # Pronunciation and regional labels
    sounds = entry.get("sounds") or []
    ipas, dialects = [], []
    if isinstance(sounds, list):
        for sound in sounds:
            if not isinstance(sound, dict):
                continue
            ipa = clean(sound.get("ipa"))
            if ipa and ipa not in ipas:
                ipas.append(ipa)
            for tag in sound.get("tags") or []:
                tag = clean(tag)
                if tag and tag not in dialects:
                    dialects.append(tag)
    if ipas:
        blocks.append("**Pronunciation (IPA):** " + "; ".join(ipas[:8]))
    if dialects:
        blocks.append("**Pronunciation labels:** " + ", ".join(dialects[:8]))

    senses = entry.get("senses") or []
    sense_blocks = []
    if isinstance(senses, list):
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            glosses = sense.get("glosses") or []
            gloss = clean(glosses[0]) if glosses else clean(sense.get("gloss"))
            if not gloss:
                continue
            labels = []
            for key in ("tags", "raw_tags", "topics", "register"):
                labels.extend(list_strings(sense.get(key)))
            label_text = f" *({', '.join(labels[:8])})*" if labels else ""
            item = f"- {gloss}{label_text}"

            examples = sense.get("examples") or []
            if isinstance(examples, list):
                for ex in examples[:2]:
                    if isinstance(ex, dict):
                        example = clean(ex.get("text"))
                        translation = clean(ex.get("translation"))
                        if example:
                            item += f"\n  - Example: “{example}”"
                            if translation:
                                item += f" ({translation})"
            sense_blocks.append(item)
    if sense_blocks:
        blocks.append("**Definitions**\n" + "\n".join(sense_blocks))

    # Lexical relations can be dictionaries or strings depending on extraction.
    for key, heading in (("synonyms", "Synonyms"), ("antonyms", "Antonyms")):
        vals = list_strings(entry.get(key))
        if vals:
            blocks.append(f"**{heading}:** " + ", ".join(vals[:30]))

    etymology = clean(entry.get("etymology_text"))
    if etymology:
        blocks.append("**Etymology:** " + etymology)

    return "\n\n".join(blocks)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-headwords", type=int, default=100000)
    args = parser.parse_args()

    Path("build").mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("""CREATE TABLE entries (
        word TEXT NOT NULL,
        sortword TEXT NOT NULL,
        pos TEXT NOT NULL,
        body TEXT NOT NULL,
        PRIMARY KEY(word, pos, body)
    )""")

    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    print(f"Downloading and streaming: {SOURCE_URL}", flush=True)
    seen = 0
    inserted = 0
    batch = []
    with urllib.request.urlopen(request, timeout=180) as response:
        with gzip.GzipFile(fileobj=response) as stream:
            for raw_line in stream:
                if not raw_line.strip():
                    continue
                seen += 1
                try:
                    entry = json.loads(raw_line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if entry.get("lang_code") != "en":
                    continue
                word = clean(entry.get("word"))
                if not word or is_form_entry(entry):
                    continue
                # Exclude entries with no usable English definition.
                senses = entry.get("senses") or []
                if not any(isinstance(s, dict) and (s.get("glosses") or s.get("gloss")) for s in senses):
                    continue
                pos = clean(entry.get("pos")) or "other"
                body = entry_to_markdown(entry)
                if not body:
                    continue
                batch.append((word, word.casefold(), pos, body))
                if len(batch) >= 1000:
                    before = db.total_changes
                    db.executemany(
                        "INSERT OR IGNORE INTO entries(word, sortword, pos, body) VALUES(?,?,?,?)",
                        batch,
                    )
                    inserted += db.total_changes - before
                    db.commit()
                    batch.clear()
                if seen % 2_000_000 == 0:
                    print(f"Scanned {seen:,} records; stored {inserted:,} entries", flush=True)

    if batch:
        before = db.total_changes
        db.executemany(
            "INSERT OR IGNORE INTO entries(word, sortword, pos, body) VALUES(?,?,?,?)",
            batch,
        )
        inserted += db.total_changes - before
        db.commit()

    count = db.execute("SELECT COUNT(DISTINCT word) FROM entries").fetchone()[0]
    print(f"Distinct English headwords with definitions: {count:,}", flush=True)
    if count < args.min_headwords:
        print(f"ERROR: only {count:,} headwords; minimum required is {args.min_headwords:,}.", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cursor = db.execute("SELECT word, pos, body FROM entries ORDER BY sortword, pos")
    current_letter = None
    file_handle = None
    words_in_file = 0
    file_count = 0
    for word, pos, body in cursor:
        letter = word[0].upper() if word and word[0].isalpha() else "0-9"
        if letter != current_letter:
            if file_handle:
                file_handle.close()
            current_letter = letter
            file_handle = (OUT_DIR / f"{letter}.md").open("w", encoding="utf-8")
            file_handle.write(f"# {letter} — Ensu English Dictionary\n\n")
            words_in_file = 0
            file_count += 1
        file_handle.write(body + "\n\n---\n\n")
        words_in_file += 1
    if file_handle:
        file_handle.close()

    db.close()
    Path("build/README-IMPORT.md").write_text(
        "# Import into Ensu\n\n"
        "1. Extract this ZIP.\n"
        "2. Import or copy the `dictionary` folder into Ensu's notes folder.\n"
        "3. Let Ensu finish indexing before asking questions.\n\n"
        "Each Markdown file contains alphabetically grouped English entries. "
        "Definitions and metadata are included only when present in the source; "
        "the model should not fill missing dictionary fields by guessing.\n",
        encoding="utf-8",
    )
    Path("build/BUILD-INFO.txt").write_text(
        f"Project: Ensu English Dictionary\n"
        f"Built: {dt.datetime.now(dt.timezone.utc).isoformat()}\n"
        f"Source: {SOURCE_URL}\n"
        f"Source page: https://kaikki.org/dictionary/rawdata.html\n"
        f"Distinct English headwords with definitions: {count}\n"
        f"Stored entry records: {inserted}\n"
        f"Minimum headwords required: {args.min_headwords}\n"
        f"Source license: Wiktionary-derived content; follow applicable CC BY-SA / GFDL terms.\n",
        encoding="utf-8",
    )
    print(f"Created {file_count} Markdown files in {OUT_DIR}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
