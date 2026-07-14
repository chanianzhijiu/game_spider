---
name: game-script-spider
description: Crawl public visual novel, interactive fiction, otome, Ren'Py, Ink, or KiriKiri game sources to discover free game packages, download allowed archives through normal site flows, extract .rpy/.ink/.ks script candidates, and prepare scene/choice/branch/effect/end story-tree analysis. Use when Codex needs to work with LemmaSoft, itch.io, VNDB, Steam/GameJolt discovery pages, temporary signed download URLs, Ren'Py packages, or branching narrative script datasets.
---

# Game Script Spider

Use this skill to build or run a compliant crawler for branching narrative game scripts. The goal is not to mirror games; it is to collect public package metadata, download allowed archives when needed, identify script files, and produce auditable inputs for story-tree extraction.

## Core Workflow

1. Discover candidates from forum or catalog pages.
   - Treat LemmaSoft Completed Games as a discovery index, not the primary script source.
   - Capture source URL, title, author, tags, free/complete markers, outbound release links, and VNDB matches.
   - Prefer saved HTML parsing when direct HTTP automation is blocked by Cloudflare or forum controls.
2. Classify release pages.
   - For itch.io pages, parse upload metadata: `upload_id`, filename, file size, platform, price/free state.
   - Skip login walls, paywalls, CAPTCHA, age gates, private files, and permission errors.
   - Do not bypass platform controls or reuse expired signed URLs.
3. Download only allowed archives.
   - For itch.io, click the public Download button or use the page's normal download-generation flow.
   - The final `itchio-mirror...X-Amz-Signature` URL is temporary; use it immediately and never store it as a durable URL.
   - Write `.part` files first, rename after completion, and record SHA256, byte length, source URL, `upload_id`, and timestamp in a manifest.
4. Inspect archives before broad extraction.
   - Scan zip entries for script candidates: `.rpy`, `.rpyc`, `.ink`, `.ks`, Ink JSON, or game-specific narrative JSON.
   - Prefer plaintext scripts (`.rpy/.ink/.ks`). Mark `.rpyc` as compiled and do not automatically decompile unless the user explicitly approves and the license/use case permits it.
5. Prepare story-tree analysis.
   - Use `references/story_tree_schema.md` for target fields.
   - For Ren'Py: identify `label`, `menu`, `jump`, `call`, `return`, `if/elif/else`, and variable effects.
   - For Ink: identify knots, stitches, choices, diverts, variables, and assignments.
   - For KiriKiri `.ks`: identify labels, `[link]`, `[jump]`, `[if]`, `[eval]`, and `[return]`.

## Safety Boundaries

- Respect `robots.txt`, platform terms, and page-visible access controls.
- Never bypass authentication, CAPTCHA, paid access, private files, or permission errors.
- Do not mass-download by default. Start with a single game or a small reviewed queue, then scale only after disk, bandwidth, and permission checks.
- Store metadata and structural outputs. Do not publish full copyrighted script text unless the license allows redistribution.
- Keep signed download URLs out of long-term manifests; record only host/path, generation time, expiry, status, and hashes.

## Resource Guide

- Read `references/site_patterns.md` when dealing with LemmaSoft, itch.io, temporary signed URLs, or download triage.
- Read `references/story_tree_schema.md` before generating JSON/Mermaid outputs for scene/choice/branch/effect/end validation.
- Use `scripts/inspect_itch_page.py` on saved itch.io HTML to extract upload metadata without downloading.
- Use `scripts/scan_archive_scripts.py` to list candidate script files inside zip archives.
- Use the repository-root `lemmasoft_free_windows_spider.py` for full LemmaSoft-only runs that require free-title filtering, Windows upload selection, resumable browser crawling, downloading, manifests, and script extraction.

## Expected Deliverables

For a download run, produce a folder like:

```text
downloads_free/<slug>/
  manifest.json
  <archive>.zip
```

For a script inspection run, produce:

```text
analysis/<slug>/
  script_inventory.json
  story_tree.json
  story_tree.md
```

Manifest fields should include source page URL, discovered page URL, filename, upload/platform identifiers, byte length, SHA256, status, and any skip reason.
