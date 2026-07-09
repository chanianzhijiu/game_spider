# game_spider

This repository stores reusable Codex skills and helper scripts for collecting public branching narrative game packages and preparing them for script/story-tree analysis.

## Skills

### game-script-spider

Path: `skills/game-script-spider`

Use this skill when working with:

- LemmaSoft Completed Games discovery pages
- itch.io public/free visual novel release pages
- VNDB metadata matching
- Ren'Py / Ink / KiriKiri script discovery
- story-tree outputs with `scene`, `choice_group`, `branch`, `effect`, and `end` nodes

The skill emphasizes compliant collection:

- do not bypass login, CAPTCHA, paywalls, private files, or permission errors;
- do not reuse temporary signed download URLs;
- store metadata, manifests, hashes, and structural story-tree outputs;
- prefer `.rpy`, `.ink`, and `.ks` source scripts over compiled-only files.

## Included Helpers

- `inspect_itch_page.py`: extract itch.io upload metadata from saved HTML.
- `scan_archive_scripts.py`: scan zip archives for `.rpy`, `.rpyc`, `.ink`, `.ks`, and JSON script candidates.
- `download_signed_url.py`: download a freshly generated signed URL to disk with SHA256 manifest metadata.

## Typical Flow

1. Discover candidate games from LemmaSoft or another public index.
2. Normalize title metadata with VNDB.
3. Inspect release pages for public/free downloadable archives.
4. Download allowed packages through normal site flows.
5. Scan archives for narrative scripts.
6. Convert script control flow into story-tree JSON/Mermaid artifacts.

