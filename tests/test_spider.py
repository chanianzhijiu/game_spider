from __future__ import annotations

import tempfile
import unittest
import zipfile
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


if __name__ == "__main__":
    unittest.main()
