# LemmaSoft Free Windows Game Spider

This repository contains a complete crawler for the LemmaSoft `Completed Games` forum:

`https://lemmasoft.renai.us/forums/viewforum.php?f=11`

The crawler only indexes topics explicitly marked `FREE` or `freeware`, excludes demo-only entries, and only downloads packages identified as Windows/PC builds.

## Install

Python 3.10 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Run

### Recommended: skip LemmaSoft and use VNDB-matched release pages

Cloudflare may reject every Playwright-controlled browser even though ordinary Chrome can open LemmaSoft. The repository therefore includes a candidate table built by matching the previously collected 46-page free-topic catalog against VNDB's official freeware Windows releases. This mode never opens LemmaSoft:

```powershell
python .\lemmasoft_free_windows_spider.py `
  --candidate-csv .\data\lemmasoft_vndb_free_windows_itch_candidates.csv `
  --output-dir F:\lemmasoft_data `
  --profile-dir "$env:LOCALAPPDATA\game_spider\itch_profile" `
  --browser-channel chrome `
  --download `
  --release-delay 5 `
  --verbose
```

The snapshot contains only title-matched, official, non-patch, non-demo VNDB releases marked freeware with Windows support and an itch.io external link. Each itch.io page is still checked for a public Windows upload before downloading. Ambiguous, unavailable, paid, or permission-protected files are skipped or left for review.

Use `--limit-topics 3` without `--download` for the first test. Progress remains resumable through `state.json`.

Build the free-game catalog without downloading packages:

```powershell
python .\lemmasoft_free_windows_spider.py --output-dir .\lemmasoft_spider_output
```

Download eligible Windows packages and extract script candidates from zip files:

```powershell
python .\lemmasoft_free_windows_spider.py --output-dir .\lemmasoft_spider_output --download
```

Chromium runs visibly by default. If Cloudflare asks for verification, complete it manually in the opened browser. The persistent profile is reused on later runs.

If ordinary Google Chrome can open the forum but Playwright's bundled Chromium remains on Cloudflare's verification page, use the installed stable Chrome with a local persistent profile:

```powershell
python .\lemmasoft_free_windows_spider.py `
  --output-dir F:\lemmasoft_data `
  --profile-dir "$env:LOCALAPPDATA\game_spider\lemmasoft_browser_profile" `
  --browser-channel chrome `
  --max-pages 1 `
  --limit-topics 3 `
  --challenge-timeout 900 `
  --verbose
```

Use `--browser-channel msedge` instead when Microsoft Edge is available but Google Chrome is not. These options still use a visible Playwright-controlled browser and require the user to complete any verification manually; they do not bypass Cloudflare.

Run the same command again after an interruption. `state.json` stores page, topic, release-page, and download progress.

Useful options:

- `--max-pages 46`: number of forum pages, default `46`.
- `--limit-topics 5`: small local test run after forum indexing.
- `--browser-channel chrome`: use installed Google Chrome; `msedge` and bundled `chromium` are also supported.
- `--headless`: use only after the persistent browser profile has passed verification.
- `--no-extract-scripts`: keep packages without extracting `.rpy/.rpyc/.ink/.ks` candidates.
- `--fresh`: reset crawl state while leaving downloaded files on disk.

## Outputs

```text
lemmasoft_spider_output/
  state.json
  summary.json
  lemmasoft_free_windows_catalog.csv
  lemmasoft_free_windows_catalog.jsonl
  games/
    <topic-id>-<slug>/
      manifest.json
      packages/
      scripts/
```

The program does not bypass authentication, CAPTCHA, paid access, private files, or permission errors. Ambiguous generic archives and unsupported release hosts are left for manual review.

## Skills

### game-script-spider

Path: `skills/game-script-spider`

Use this skill when extending or reviewing the crawler:

- LemmaSoft Completed Games discovery pages
- itch.io public/free visual novel release pages
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

1. Discover explicitly free games from LemmaSoft.
2. Inspect each topic's public release links.
3. Select Windows builds, including itch.io uploads with Windows platform metadata.
4. Download through normal site flows and write SHA256 manifests.
5. Extract narrative script candidates from zip archives.
6. Convert script control flow into story-tree JSON/Mermaid artifacts.
