from __future__ import annotations

import tempfile
import unittest
import zipfile
import csv
from pathlib import Path

import lemmasoft_free_windows_spider as spider


class SpiderParserTests(unittest.TestCase):
    def test_free_title_filter(self) -> None:
        self.assertTrue(spider.is_explicitly_free("Example [FREE]"))
        self.assertTrue(spider.is_explicitly_free("Example freeware"))
        self.assertFalse(spider.is_explicitly_free("Example free demo"))
        self.assertFalse(spider.is_explicitly_free("Example demo"))

    def test_windows_scoring(self) -> None:
        self.assertGreaterEqual(spider.direct_windows_score("Windows", "https://x/game.zip"), 80)
        self.assertGreaterEqual(spider.direct_windows_score("", "https://x/game.exe"), 80)
        self.assertLess(spider.direct_windows_score("macOS", "https://x/game-osx.zip"), 0)
        self.assertEqual(spider.direct_windows_score("download", "https://x/game.zip"), 10)

    def test_itch_upload_parser(self) -> None:
        html = """
        <div class="upload">
          <a class="download_btn" data-upload_id="1">Download</a>
          <div class="upload_name"><strong class="name" title="game-win.zip">game-win.zip</strong></div>
          <span class="file_size">100 MB</span>
          <span class="download_platforms"><span title="Download for Windows"></span></span>
        </div>
        <div class="upload">
          <a class="download_btn" data-upload_id="2">Download</a>
          <div class="upload_name"><strong class="name" title="game-osx.zip">game-osx.zip</strong></div>
          <span class="download_platforms"><span title="Download for macOS"></span></span>
        </div>
        """
        uploads = spider.parse_itch_uploads(html, "https://example.itch.io/game")
        self.assertEqual(2, len(uploads))
        self.assertTrue(uploads[0].is_windows)
        self.assertFalse(uploads[1].is_windows)

    def test_zip_script_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "game.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("game/script.rpy", "label start:\n    return\n")
                handle.writestr("renpy/common/engine.rpy", "label engine:\n    return\n")
                handle.writestr("assets/config.json", "{}")
                handle.writestr("game/archive.rpa", b"RPA-3.0")
            result = spider.inspect_and_extract_zip(archive, root / "scripts")
            self.assertEqual(1, result["script_count"])
            self.assertEqual("game/script.rpy", result["scripts"][0]["archive_path"])
            self.assertEqual("game/archive.rpa", result["packed_containers"][0]["archive_path"])

    def test_candidate_csv_import_skips_unsupported_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_csv = root / "candidates.csv"
            with candidate_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["topic_id", "title", "clean_title", "forum_url", "external_url", "release_id"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "topic_id": "1",
                        "title": "Example [FREE]",
                        "clean_title": "Example",
                        "forum_url": "https://lemmasoft.renai.us/forums/viewtopic.php?t=1",
                        "external_url": "https://author.itch.io/example",
                        "release_id": "r1",
                    }
                )
                writer.writerow(
                    {
                        "topic_id": "2",
                        "title": "Unsupported [FREE]",
                        "clean_title": "Unsupported",
                        "forum_url": "https://lemmasoft.renai.us/forums/viewtopic.php?t=2",
                        "external_url": "https://example.invalid/game",
                        "release_id": "r2",
                    }
                )
            store = spider.Store(root / "output")
            self.assertEqual(1, spider.import_candidate_csv(candidate_csv, store))
            self.assertEqual(["1"], list(store.data["topics"]))
            self.assertEqual("https://author.itch.io/example", store.data["topics"]["1"]["release_links"][0]["url"])


if __name__ == "__main__":
    unittest.main()
