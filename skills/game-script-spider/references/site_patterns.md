# Site Patterns

## LemmaSoft Completed Games

Use LemmaSoft as a discovery index.

Known behavior:

- `viewforum.php?f=11` is the Completed Games forum.
- Pages are offset by `start=60`, `start=120`, etc.
- Topic rows contain `viewtopic.php?t=<id>`, author links, timestamps, reply/view counts, and title tags such as `[FREE]`, `[COMPLETE]`, `[Otome]`.
- Direct script HTTP requests may receive 403 in some environments while browsers work. Prefer browser-saved HTML or a browser-controlled read path instead of trying to bypass Cloudflare.

Recommended fields:

- `topic_id`
- `title`
- `clean_title`
- `author`
- `topic_url`
- `posted_at`
- `last_post_at`
- `replies`
- `views`
- `tags`
- `external_links`
- `possible_download_links`

## itch.io Release Pages

Use itch as a release/download page.

Important details:

- Public download buttons are often anchors like `a.download_btn[data-upload_id]` with `href="javascript:void(0)"`.
- The page may expose a `generate_download_url` endpoint in JS.
- Clicking Download usually inserts a hidden iframe pointing to a Cloudflare R2 / S3 signed URL.
- Signed URLs commonly contain `X-Amz-Date`, `X-Amz-Expires`, and `X-Amz-Signature`.
- `X-Amz-Expires=60` means the URL is short-lived. If a lightbox is closed, the page is refreshed, or an old URL is retried later, the server may return permission/expired errors.

Correct crawler behavior:

- Store `game_page_url`, `upload_id`, filename, size, platform, and source topic.
- Generate the signed URL immediately before downloading.
- Start the download immediately and write to `<filename>.part` until complete.
- Rename only after success.
- Record SHA256, byte count, HTTP status, signed URL host/path, `X-Amz-Date`, and `X-Amz-Expires`.
- Do not store or reuse the full signed URL as a durable download URL.

Skip conditions:

- Login required.
- Paid checkout required.
- CAPTCHA or age verification blocks access.
- The page says the file is unavailable or private.
- The platform returns 401/403 that is not an ordinary expired signed URL from a just-generated public flow.

## VNDB

Use VNDB for normalization and deduplication, not package downloads.

Useful endpoint:

- `POST https://api.vndb.org/kana/vn`

Typical payload:

```json
{
  "filters": ["search", "=", "Game Title"],
  "fields": "id,title,alttitle,aliases,released,languages,platforms,image.url,developers.name,rating,votecount",
  "sort": "searchrank",
  "results": 3
}
```

Keep low-confidence matches as candidates instead of auto-merging.

