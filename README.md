# Ensu English Dictionary

A cloud-built, offline English dictionary for Ensu's local AI notes/indexing feature.

## What this project does

- Downloads structured Wiktionary data extracted by Wiktextract from Kaikki.org.
- Keeps English-language lexical entries and skips entries explicitly marked as inflected forms.
- Builds alphabetically organized Markdown files for Ensu.
- Includes definitions, parts of speech, IPA pronunciations, usage labels, examples, synonyms, antonyms, and etymology when available.
- Creates a ZIP artifact in GitHub Actions so it can be downloaded to an Android phone.

**Important:** This is a Wiktionary-derived reference, not an Oxford, Cambridge, or Merriam-Webster product. Coverage and editorial quality vary. Missing fields are omitted rather than invented.

## Build

1. Create a GitHub repository named `ensu-english-dictionary`.
2. Upload the project files, preserving their folder paths.
3. Open **Actions** → **Build Ensu English Dictionary**.
4. Press **Run workflow**.
5. When it finishes, open the workflow run and download `ensu-english-dictionary`.
6. Extract the ZIP on your phone and import the Markdown folder into Ensu's notes/indexing area.

The first build downloads a large compressed Wiktextract data file (currently about 2.9 GB). The workflow streams it; it does not save a 24.8 GB uncompressed dump to disk. Source data sizes and versions can change.

## Output

The generated ZIP contains:

- `dictionary/A.md` ... `dictionary/Z.md` — alphabetically sorted Markdown shards
- `README-IMPORT.md` — import guidance and source notes
- `BUILD-INFO.txt` — source URL, build date, and word count

The builder aims for at least 100,000 distinct English headwords. It stops with a clear error if the source data does not provide that many eligible entries.

## Source and licensing

The source is Wiktionary content extracted by Wiktextract and distributed by Kaikki.org. Wiktionary text is generally available under the Creative Commons Attribution-ShareAlike (CC BY-SA) and/or GNU Free Documentation License (GFDL), subject to the specific source page and applicable terms. This project includes attribution and a source link; users redistributing the generated dataset must follow the applicable license terms.

- Data downloads: https://kaikki.org/dictionary/rawdata.html
- Wiktextract: https://github.com/tatuylonen/wiktextract
- Wiktionary: https://en.wiktionary.org/

This project does not copy Oxford, Cambridge, or Merriam-Webster proprietary dictionary text.
