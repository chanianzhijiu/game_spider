#!/usr/bin/env python3
"""Crawl LemmaSoft Completed Games for explicitly free Windows packages.

The crawler uses a real Chromium session because LemmaSoft and some linked
release pages may present browser verification. It does not bypass login,
CAPTCHA, paywalls, private files, or permission errors. When verification is
required, run headed and complete it manually in the opened browser.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import shutil
import sys
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - handled by doctor/main
    BrowserContext = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None


DEFAULT_FORUM_URL = "https://lemmasoft.renai.us/forums/viewforum.php?f=11"
FORUM_ROOT = "https://lemmasoft.renai.us/forums/"
USER_AGENT = "game-script-spider/1.0 (public free Windows package indexer)"

FREE_TITLE_RE = re.compile(r"(^|[\s\[\(\-])free(?:ware)?([\s\]\)\-]|$)", re.I)
DEMO_ONLY_RE = re.compile(r"free\s+demo|demo\s+only", re.I)
WINDOWS_RE = re.compile(r"\b(?:windows?|win(?:32|64)?|pc)\b", re.I)
NON_WINDOWS_RE = re.compile(r"\b(?:mac(?:os)?|osx|linux|android|apk|ios)\b", re.I)
DIRECT_ARCHIVE_EXTENSIONS = (".zip", ".exe", ".msi", ".7z", ".rar")
SCRIPT_EXTENSIONS = (".rpy", ".rpyc", ".ink", ".ks")
JSON_SCRIPT_HINTS = ("script", "story", "scenario", "dialog", "narrative", "ink")
SUPPORTED_RELEASE_HOSTS = ("itch.io", "gamejolt.com", "drive.google.com", "mediafire.com", "mega.nz")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_session_id(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query.pop("sid", None)
    pairs = [(key, value) for key, values in query.items() for value in values]
    return urlunparse(parsed._replace(query=urlencode(pairs), fragment=""))


def absolute_forum_url(href: str) -> str:
    return strip_session_id(urljoin(FORUM_ROOT, href))


def clean_title(title: str) -> str:
    value = re.sub(r"\[[^\]]+\]", " ", title)
    value = re.sub(r"\([^)]*(?:free|complete|demo|otome jam|nanoreno)[^)]*\)", " ", value, flags=re.I)
    value = re.split(r"\s+-\s+|\s+\\\\\s+|\s+\|\s+", value, maxsplit=1)[0]
    return normalize_space(value).strip(" :-")


def extract_tags(title: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for group in re.findall(r"\[([^\]]+)\]", title):
        for raw in re.split(r"[,/|]", group):
            tag = normalize_space(raw)
            key = tag.lower()
            if tag and key not in seen:
                seen.add(key)
                tags.append(tag)
    return tags


def is_explicitly_free(title: str) -> bool:
    return bool(FREE_TITLE_RE.search(title)) and not bool(DEMO_ONLY_RE.search(title))


def safe_slug(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._").lower()
    return value[:100] or fallback


def safe_filename(value: str, fallback: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", value).strip(" .")
    return value[:180] or fallback


def parse_number_before(text: str, label: str) -> int | None:
    match = re.search(rf"(\d[\d,]*)\s+{re.escape(label)}", text, re.I)
    return int(match.group(1).replace(",", "")) if match else None


def is_release_page(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == item or host.endswith("." + item) for item in SUPPORTED_RELEASE_HOSTS)


def direct_windows_score(text: str, url: str) -> int:
    combined = f"{text} {url}"
    path = urlparse(url).path.lower()
    if path.endswith((".dmg", ".apk")):
        return -100
    if NON_WINDOWS_RE.search(combined) and not WINDOWS_RE.search(combined):
        return -50
    if path.endswith((".exe", ".msi")):
        return 100
    if WINDOWS_RE.search(combined) and path.endswith(DIRECT_ARCHIVE_EXTENSIONS):
        return 80
    if path.endswith(DIRECT_ARCHIVE_EXTENSIONS):
        return 10  # Keep for review, but do not auto-download.
    return 0


@dataclass
class LinkInfo:
    text: str
    url: str
    host: str
    kind: str
    windows_score: int = 0


@dataclass
class TopicInfo:
    topic_id: str
    title: str
    clean_title: str
    url: str
    author: str | None = None
    posted_at: str | None = None
    last_post_at: str | None = None
    replies: int | None = None
    views: int | None = None
    tags: list[str] = field(default_factory=list)
    page_number: int | None = None
    is_free: bool = True
    excerpt: str | None = None
    external_links: list[dict[str, Any]] = field(default_factory=list)
    release_links: list[dict[str, Any]] = field(default_factory=list)
    topic_status: str = "indexed"
    error: str | None = None
    updated_at: str = field(default_factory=utc_now)


@dataclass
class UploadInfo:
    upload_id: str
    filename: str
    size_label: str
    platforms: list[str]
    is_windows: bool
    source_url: str


class Store:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.state_path = output_dir / "state.json"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "version": 1,
            "forum_pages_done": [],
            "topics": {},
            "release_pages": {},
            "downloads": {},
            "updated_at": utc_now(),
        }
        if self.state_path.exists():
            self.data = json.loads(self.state_path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.data["updated_at"] = utc_now()
        temp = self.state_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def reset_progress(self) -> None:
        self.data["forum_pages_done"] = []
        self.data["topics"] = {}
        self.data["release_pages"] = {}
        self.data["downloads"] = {}
        self.save()

    def upsert_topic(self, topic: TopicInfo) -> None:
        existing = self.data["topics"].get(topic.topic_id, {})
        merged = {**existing, **asdict(topic)}
        self.data["topics"][topic.topic_id] = merged

    def topics(self) -> list[dict[str, Any]]:
        return list(self.data["topics"].values())


def import_candidate_csv(path: Path, store: Store) -> int:
    """Import pre-matched public release pages without visiting LemmaSoft."""
    imported_links = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"topic_id", "title", "forum_url", "external_url"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Candidate CSV is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            topic_id = normalize_space(row.get("topic_id"))
            title = normalize_space(row.get("title"))
            external_url = normalize_space(row.get("external_url"))
            if not topic_id or not title or not external_url or not is_release_page(external_url):
                continue
            topic = store.data["topics"].get(topic_id)
            if topic is None:
                topic = asdict(
                    TopicInfo(
                        topic_id=topic_id,
                        title=title,
                        clean_title=normalize_space(row.get("clean_title")) or clean_title(title),
                        url=normalize_space(row.get("forum_url")),
                        author=normalize_space(row.get("author")) or None,
                        tags=[value.strip() for value in (row.get("tags") or "").split(";") if value.strip()],
                        topic_status="candidate_imported",
                    )
                )
                topic["vndb_releases"] = []
            link = asdict(
                LinkInfo(
                    text=normalize_space(row.get("release_title")) or title,
                    url=external_url,
                    host=urlparse(external_url).netloc.lower(),
                    kind="release_page",
                )
            )
            known_urls = {item.get("url") for item in topic.get("release_links", [])}
            if external_url not in known_urls:
                topic.setdefault("external_links", []).append(link)
                topic.setdefault("release_links", []).append(link)
                imported_links += 1
            release_id = normalize_space(row.get("release_id"))
            known_releases = {item.get("release_id") for item in topic.get("vndb_releases", [])}
            if release_id and release_id not in known_releases:
                topic.setdefault("vndb_releases", []).append(
                    {
                        "release_id": release_id,
                        "release_title": normalize_space(row.get("release_title")),
                        "vn_id": normalize_space(row.get("vn_id")),
                        "vn_title": normalize_space(row.get("vn_title")),
                        "released": normalize_space(row.get("released")),
                        "platforms": normalize_space(row.get("platforms")),
                        "languages": normalize_space(row.get("languages")),
                        "engine": normalize_space(row.get("engine")),
                        "release_url": normalize_space(row.get("release_url")),
                        "vn_url": normalize_space(row.get("vn_url")),
                    }
                )
            topic["updated_at"] = utc_now()
            store.data["topics"][topic_id] = topic
    store.save()
    return imported_links


class BrowserCrawler:
    def __init__(self, args: argparse.Namespace, store: Store) -> None:
        self.args = args
        self.store = store
        self.playwright = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})

    def __enter__(self) -> "BrowserCrawler":
        if sync_playwright is None:
            raise RuntimeError("Playwright is not installed. Run: pip install -r requirements.txt")
        self.playwright = sync_playwright().start()
        self.args.profile_dir.mkdir(parents=True, exist_ok=True)
        launch_options: dict[str, Any] = {
            "user_data_dir": str(self.args.profile_dir.resolve()),
            "headless": self.args.headless,
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 900},
        }
        if self.args.browser_channel != "chromium":
            launch_options["channel"] = self.args.browser_channel
        logging.info("Launching browser channel: %s", self.args.browser_channel)
        self.context = self.playwright.chromium.launch_persistent_context(**launch_options)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def paced(self, delay: float | None = None) -> None:
        time.sleep(self.args.delay if delay is None else delay)

    def navigate(self, url: str, ready_selector: str, *, allow_manual_verification: bool = True) -> None:
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded", timeout=self.args.navigation_timeout * 1000)
        deadline = time.monotonic() + self.args.challenge_timeout
        announced = False
        while True:
            title = self.page.title()
            verification = (
                "just a moment" in title.lower()
                or "checking your browser" in title.lower()
                or "请稍候" in title
                or self.page.locator("iframe[src*='challenges.cloudflare.com'], .cf-turnstile").count() > 0
            )
            if self.page.locator(ready_selector).count() > 0 and not verification:
                return
            if not allow_manual_verification or time.monotonic() >= deadline:
                raise RuntimeError(f"Page did not become ready: {url} (title={title!r})")
            if not announced:
                logging.warning(
                    "Waiting for browser verification at %s. Complete it manually in the opened %s window.",
                    url,
                    self.args.browser_channel,
                )
                announced = True
            self.page.wait_for_timeout(1000)

    def crawl_forum_pages(self) -> None:
        done = set(self.store.data.get("forum_pages_done", []))
        for page_number in range(1, self.args.max_pages + 1):
            if page_number in done:
                continue
            offset = (page_number - 1) * 60
            url = self.args.forum_url if offset == 0 else f"{self.args.forum_url}&start={offset}"
            logging.info("Forum page %s/%s: %s", page_number, self.args.max_pages, url)
            self.navigate(url, "li.row a[href*='viewtopic.php?t=']")
            assert self.page is not None
            topics = parse_forum_page(self.page.content(), page_number)
            if not topics:
                raise RuntimeError(f"No topics parsed from forum page {page_number}")
            for topic in topics:
                if topic.is_free:
                    self.store.upsert_topic(topic)
            self.store.data["forum_pages_done"].append(page_number)
            self.store.save()
            self.paced()

    def crawl_topic_details(self) -> None:
        topics = sorted(self.store.topics(), key=lambda row: (row.get("page_number") or 0, row["topic_id"]))
        if self.args.limit_topics:
            topics = topics[: self.args.limit_topics]
        for index, raw in enumerate(topics, 1):
            if raw.get("topic_status") == "inspected" and not self.args.refresh_topics:
                continue
            logging.info("Topic %s/%s: %s", index, len(topics), raw["title"])
            try:
                self.navigate(raw["url"], ".post, .postbody")
                assert self.page is not None
                excerpt, links = parse_topic_page(self.page.content())
                release_links = [asdict(link) for link in links if link.kind in {"release_page", "direct_archive"}]
                raw.update(
                    {
                        "excerpt": excerpt,
                        "external_links": [asdict(link) for link in links],
                        "release_links": release_links,
                        "topic_status": "inspected",
                        "error": None,
                        "updated_at": utc_now(),
                    }
                )
            except Exception as exc:  # Keep the run resumable per topic.
                logging.exception("Topic failed: %s", raw["url"])
                raw.update({"topic_status": "error", "error": str(exc), "updated_at": utc_now()})
            self.store.data["topics"][raw["topic_id"]] = raw
            self.store.save()
            self.paced(self.args.topic_delay)

    def process_downloads(self) -> None:
        topics = sorted(self.store.topics(), key=lambda row: (row.get("page_number") or 0, row["topic_id"]))
        if self.args.limit_topics:
            topics = topics[: self.args.limit_topics]
        for topic in topics:
            for link in topic.get("release_links", []):
                url = link["url"]
                host = urlparse(url).netloc.lower()
                key = f"{topic['topic_id']}:{url}"
                previous_status = self.store.data["release_pages"].get(key, {}).get("status")
                if not self.args.refresh_downloads:
                    if previous_status in {"done", "skipped", "manual_review"}:
                        continue
                    if previous_status == "cataloged" and not self.args.download:
                        continue
                try:
                    if host.endswith(".itch.io") or host == "itch.io":
                        result = self.process_itch_page(topic, url)
                    elif link.get("kind") == "direct_archive" and int(link.get("windows_score", 0)) >= 80:
                        result = self.download_direct(topic, link)
                    else:
                        result = {"status": "manual_review", "reason": "unsupported or ambiguous release host"}
                except Exception as exc:
                    logging.exception("Release page failed: %s", url)
                    result = {"status": "error", "error": str(exc)}
                result.update({"source_url": url, "updated_at": utc_now()})
                self.store.data["release_pages"][key] = result
                self.store.save()
                self.paced(self.args.release_delay)

    def process_itch_page(self, topic: dict[str, Any], url: str) -> dict[str, Any]:
        self.navigate(url, "body", allow_manual_verification=True)
        assert self.page is not None
        self.reveal_itch_free_uploads()
        uploads = parse_itch_uploads(self.page.content(), url)
        windows_uploads = [upload for upload in uploads if upload.is_windows]
        if not windows_uploads:
            return {"status": "skipped", "reason": "no public Windows upload", "uploads": [asdict(x) for x in uploads]}
        downloaded = []
        for upload in windows_uploads:
            upload_key = f"itch:{upload.upload_id}"
            if self.store.data["downloads"].get(upload_key, {}).get("status") == "downloaded" and not self.args.refresh_downloads:
                downloaded.append(self.store.data["downloads"][upload_key])
                continue
            if not self.args.download:
                item = {**asdict(upload), "status": "candidate"}
            else:
                item = self.download_itch_upload(topic, upload)
            self.store.data["downloads"][upload_key] = item
            self.store.save()
            self.write_game_manifest(topic)
            downloaded.append(item)
        status = "done" if self.args.download else "cataloged"
        return {"status": status, "uploads": [asdict(x) for x in uploads], "windows_results": downloaded}

    def reveal_itch_free_uploads(self) -> None:
        """Follow itch's normal pay-what-you-want free-download path when present."""
        assert self.page is not None
        if self.page.locator("a.download_btn[data-upload_id]").count() > 0:
            return
        download_now = self.page.get_by_text("Download Now", exact=True)
        if download_now.count() != 1:
            return
        download_now.click()
        no_thanks = self.page.get_by_text("No thanks, just take me to the downloads", exact=False).first
        try:
            no_thanks.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeoutError:
            return
        no_thanks.click()
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError:
            pass
        try:
            self.page.locator("a.download_btn[data-upload_id]").first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            pass

    def download_itch_upload(self, topic: dict[str, Any], upload: UploadInfo) -> dict[str, Any]:
        assert self.page is not None
        game_dir = self.game_dir(topic)
        filename = safe_filename(upload.filename, f"itch-{upload.upload_id}.zip")
        destination = game_dir / "packages" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.stat().st_size > 0:
            return self.finish_download_record(topic, upload, destination, "existing")

        close = self.page.locator(".lightbox .close_button")
        if close.count() == 1 and close.is_visible():
            close.click()
        button = self.page.locator(f'a.download_btn[data-upload_id="{upload.upload_id}"]')
        if button.count() != 1:
            raise RuntimeError(f"itch upload button not found: {upload.upload_id}")

        existing_iframes = set(
            self.page.locator("iframe[src*='itchio-mirror']").evaluate_all("els => els.map(e => e.src)")
        )
        try:
            with self.page.expect_download(timeout=self.args.download_event_timeout * 1000) as event:
                button.click()
            download = event.value
            temp = destination.with_suffix(destination.suffix + ".part")
            download.save_as(str(temp))
            temp.replace(destination)
        except PlaywrightTimeoutError:
            signed_url = self.wait_for_itch_signed_url(existing_iframes)
            self.stream_download(signed_url, destination)
        return self.finish_download_record(topic, upload, destination, "downloaded")

    def wait_for_itch_signed_url(self, existing: set[str]) -> str:
        assert self.page is not None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            urls = self.page.locator("iframe[src*='itchio-mirror']").evaluate_all("els => els.map(e => e.src)")
            fresh = [url for url in urls if url not in existing]
            if fresh:
                return fresh[-1]
            self.page.wait_for_timeout(250)
        raise RuntimeError("itch did not generate a signed download URL")

    def download_direct(self, topic: dict[str, Any], link: dict[str, Any]) -> dict[str, Any]:
        filename = safe_filename(Path(urlparse(link["url"]).path).name, f"topic-{topic['topic_id']}.bin")
        destination = self.game_dir(topic) / "packages" / filename
        if self.args.download:
            self.stream_download(link["url"], destination)
            record = self.finish_download_record(topic, None, destination, "downloaded")
            self.store.data["downloads"][f"direct:{link['url']}"] = record
            self.write_game_manifest(topic)
        else:
            record = {"status": "candidate", "url": link["url"], "filename": filename}
        return {"status": "done" if self.args.download else "cataloged", "direct_result": record}

    def stream_download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".part")
        if temp.exists():
            temp.unlink()
        with self.http.get(url, stream=True, timeout=(30, self.args.download_timeout), allow_redirects=True) as response:
            response.raise_for_status()
            with temp.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temp.replace(destination)

    def finish_download_record(
        self,
        topic: dict[str, Any],
        upload: UploadInfo | None,
        destination: Path,
        status: str,
    ) -> dict[str, Any]:
        record = {
            "status": status,
            "topic_id": topic["topic_id"],
            "topic_url": topic["url"],
            "upload_id": upload.upload_id if upload else None,
            "source_url": upload.source_url if upload else None,
            "filename": destination.name,
            "path": str(destination.resolve()),
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "platforms": upload.platforms if upload else ["Windows"],
            "downloaded_at": utc_now(),
        }
        if self.args.extract_scripts and destination.suffix.lower() == ".zip":
            record["script_inventory"] = inspect_and_extract_zip(
                destination,
                self.game_dir(topic) / "scripts",
            )
        return record

    def game_dir(self, topic: dict[str, Any]) -> Path:
        slug = safe_slug(topic.get("clean_title") or topic["title"], f"topic-{topic['topic_id']}")
        return self.args.output_dir / "games" / f"{topic['topic_id']}-{slug}"

    def write_game_manifest(self, topic: dict[str, Any]) -> None:
        game_dir = self.game_dir(topic)
        game_dir.mkdir(parents=True, exist_ok=True)
        related = [value for value in self.store.data["downloads"].values() if value.get("topic_id") == topic["topic_id"]]
        manifest = {"topic": topic, "downloads": related, "updated_at": utc_now()}
        (game_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_forum_page(html: str, page_number: int) -> list[TopicInfo]:
    soup = BeautifulSoup(html, "html.parser")
    topics: list[TopicInfo] = []
    for row in soup.select("li.row"):
        classes = row.get("class", [])
        if "announce" in classes or "sticky" in classes:
            continue
        link = row.select_one("a[href*='viewtopic.php?t=']")
        if not link:
            continue
        url = absolute_forum_url(link.get("href", ""))
        topic_id = (parse_qs(urlparse(url).query).get("t") or [""])[0]
        title = normalize_space(link.get_text(" "))
        if not topic_id or not title:
            continue
        text = normalize_space(row.get_text(" "))
        author = row.select_one("dt .username, dt a[href*='memberlist.php']")
        posted = row.select_one(".list-inner time")
        last_post = row.select_one(".lastpost time")
        topics.append(
            TopicInfo(
                topic_id=topic_id,
                title=title,
                clean_title=clean_title(title),
                url=url,
                author=normalize_space(author.get_text(" ")) if author else None,
                posted_at=normalize_space(posted.get_text(" ")) if posted else None,
                last_post_at=normalize_space(last_post.get_text(" ")) if last_post else None,
                replies=parse_number_before(text, "Replies"),
                views=parse_number_before(text, "Views"),
                tags=extract_tags(title),
                page_number=page_number,
                is_free=is_explicitly_free(title),
            )
        )
    return topics


def parse_topic_page(html: str, excerpt_chars: int = 500) -> tuple[str, list[LinkInfo]]:
    soup = BeautifulSoup(html, "html.parser")
    post = soup.select_one(".postbody .content") or soup.select_one(".post .content") or soup.select_one(".post")
    if not post:
        raise RuntimeError("First post was not found")
    excerpt = normalize_space(post.get_text(" "))[:excerpt_chars]
    links: list[LinkInfo] = []
    seen: set[str] = set()
    for anchor in post.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:")):
            continue
        url = absolute_forum_url(href)
        host = urlparse(url).netloc.lower()
        if not host or host.endswith("lemmasoft.renai.us") or url in seen:
            continue
        seen.add(url)
        text = normalize_space(anchor.get_text(" "))[:160]
        score = direct_windows_score(text, url)
        if urlparse(url).path.lower().endswith(DIRECT_ARCHIVE_EXTENSIONS):
            kind = "direct_archive"
        elif is_release_page(url):
            kind = "release_page"
        else:
            kind = "external"
        links.append(LinkInfo(text=text, url=url, host=host, kind=kind, windows_score=score))
    return excerpt, links


def parse_itch_uploads(html: str, source_url: str) -> list[UploadInfo]:
    soup = BeautifulSoup(html, "html.parser")
    uploads: list[UploadInfo] = []
    for button in soup.select("a.download_btn[data-upload_id]"):
        container = button.find_parent(class_="upload")
        if not container:
            continue
        name = container.select_one(".upload_name .name")
        filename = normalize_space(name.get("title") if name and name.get("title") else name.get_text(" ") if name else "")
        size = normalize_space(container.select_one(".file_size").get_text(" ") if container.select_one(".file_size") else "")
        platforms = [normalize_space(node.get("title")) for node in container.select(".download_platforms [title]")]
        combined = f"{filename} {' '.join(platforms)}"
        has_windows = any("windows" in item.lower() for item in platforms) or bool(WINDOWS_RE.search(combined))
        only_non_windows = bool(NON_WINDOWS_RE.search(combined)) and not has_windows
        uploads.append(
            UploadInfo(
                upload_id=button.get("data-upload_id", ""),
                filename=filename or f"itch-{button.get('data-upload_id')}.bin",
                size_label=size,
                platforms=platforms,
                is_windows=has_windows and not only_non_windows,
                source_url=source_url,
            )
        )
    return uploads


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_script_candidate(name: str) -> bool:
    lower = name.lower()
    if "/renpy/common/" in "/" + lower:
        return False
    if lower.endswith(SCRIPT_EXTENSIONS):
        return True
    return lower.endswith(".json") and any(hint in lower for hint in JSON_SCRIPT_HINTS)


def safe_zip_member(name: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def inspect_and_extract_zip(archive_path: Path, output_dir: Path) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    packed_containers: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.filename.lower().endswith(".rpa"):
                packed_containers.append(
                    {
                        "archive_path": info.filename,
                        "file_size": info.file_size,
                        "kind": "renpy-archive",
                    }
                )
                continue
            if not is_script_candidate(info.filename):
                continue
            member = safe_zip_member(info.filename)
            if member is None:
                continue
            target = output_dir / archive_path.stem / Path(*member.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            inventory.append(
                {
                    "archive_path": info.filename,
                    "extracted_path": str(target.resolve()),
                    "file_size": info.file_size,
                    "extension": Path(info.filename).suffix.lower(),
                }
            )
    result = {
        "archive": str(archive_path.resolve()),
        "script_count": len(inventory),
        "scripts": inventory,
        "packed_containers": packed_containers,
        "warnings": ["Ren'Py .rpa containers were found but not unpacked."] if packed_containers else [],
    }
    inventory_path = output_dir / f"{archive_path.stem}-script-inventory.json"
    inventory_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def export_tables(store: Store) -> None:
    topics = sorted(store.topics(), key=lambda row: (row.get("page_number") or 0, row.get("topic_id", "")))
    csv_path = store.output_dir / "lemmasoft_free_windows_catalog.csv"
    jsonl_path = store.output_dir / "lemmasoft_free_windows_catalog.jsonl"
    fields = [
        "topic_id",
        "title",
        "clean_title",
        "url",
        "author",
        "posted_at",
        "last_post_at",
        "replies",
        "views",
        "tags",
        "page_number",
        "topic_status",
        "release_urls",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for topic in topics:
            writer.writerow(
                {
                    **{key: topic.get(key, "") for key in fields},
                    "tags": "; ".join(topic.get("tags", [])),
                    "release_urls": "; ".join(link.get("url", "") for link in topic.get("release_links", [])),
                }
            )
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for topic in topics:
            handle.write(json.dumps(topic, ensure_ascii=False) + "\n")
    summary = {
        "generated_at": utc_now(),
        "forum_url": DEFAULT_FORUM_URL,
        "pages_done": len(store.data.get("forum_pages_done", [])),
        "free_topics": len(topics),
        "topics_inspected": sum(topic.get("topic_status") == "inspected" for topic in topics),
        "downloaded_files": sum(value.get("status") in {"downloaded", "existing"} for value in store.data["downloads"].values()),
        "download_candidates": sum(value.get("status") == "candidate" for value in store.data["downloads"].values()),
        "errors": sum(topic.get("topic_status") == "error" for topic in topics),
    }
    (store.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Exported %s free topics to %s", len(topics), csv_path)


def run_offline(args: argparse.Namespace, store: Store) -> None:
    for page_number, html_path in enumerate(args.offline_forum_html, 1):
        html = html_path.read_text(encoding="utf-8", errors="replace")
        for topic in parse_forum_page(html, page_number):
            if topic.is_free:
                store.upsert_topic(topic)
        store.data["forum_pages_done"].append(page_number)
    store.save()
    export_tables(store)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl explicitly free LemmaSoft games and download Windows packages.")
    parser.add_argument("--forum-url", default=DEFAULT_FORUM_URL)
    parser.add_argument("--output-dir", type=Path, default=Path("lemmasoft_spider_output"))
    parser.add_argument("--profile-dir", type=Path, default=Path(".browser-profile/lemmasoft"))
    parser.add_argument(
        "--candidate-csv",
        type=Path,
        help="Import pre-matched public release URLs and skip all LemmaSoft requests.",
    )
    parser.add_argument(
        "--browser-channel",
        choices=("chromium", "chrome", "msedge"),
        default="chromium",
        help="Browser to launch. Try chrome or msedge when bundled Chromium cannot pass manual verification.",
    )
    parser.add_argument("--max-pages", type=int, default=46)
    parser.add_argument("--limit-topics", type=int, default=0, help="Development limit; 0 means all free topics.")
    parser.add_argument("--download", action="store_true", help="Download eligible Windows packages. Without this flag, build a candidate catalog only.")
    parser.add_argument("--extract-scripts", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--headless", action="store_true", help="Use only after the browser profile has passed verification.")
    parser.add_argument("--fresh", action="store_true", help="Reset crawl state but keep existing downloaded files.")
    parser.add_argument("--refresh-topics", action="store_true")
    parser.add_argument("--refresh-downloads", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--topic-delay", type=float, default=1.0)
    parser.add_argument("--release-delay", type=float, default=1.0)
    parser.add_argument("--navigation-timeout", type=int, default=45)
    parser.add_argument("--challenge-timeout", type=int, default=300)
    parser.add_argument("--download-event-timeout", type=int, default=15)
    parser.add_argument("--download-timeout", type=int, default=1800)
    parser.add_argument("--offline-forum-html", nargs="*", type=Path, help="Offline parser test; never opens the network.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    store = Store(args.output_dir)
    if args.fresh:
        store.reset_progress()
    if args.offline_forum_html:
        run_offline(args, store)
        return 0
    try:
        with BrowserCrawler(args, store) as crawler:
            if args.candidate_csv:
                imported = import_candidate_csv(args.candidate_csv, store)
                logging.info("Imported %s release links from %s; LemmaSoft will not be opened.", imported, args.candidate_csv)
            else:
                crawler.crawl_forum_pages()
                crawler.crawl_topic_details()
            crawler.process_downloads()
    except KeyboardInterrupt:
        logging.warning("Interrupted; state has been preserved for resume.")
        return 130
    except Exception as exc:
        logging.exception("Crawler stopped: %s", exc)
        return 2
    finally:
        export_tables(store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
