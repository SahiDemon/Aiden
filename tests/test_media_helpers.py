import unittest

from src.media.browser_media_controller import score_window_title
from src.media.spotify_utils import find_best_device


class BrowserMediaControllerTests(unittest.TestCase):
    def test_score_prefers_music_titles(self):
        title = "YouTube Music - Chrome"
        youtube_music_score = score_window_title(title, "youtube_music")
        youtube_score = score_window_title(title, "youtube")
        self.assertGreater(youtube_music_score, youtube_score)

    def test_score_non_matching_title(self):
        score = score_window_title("My Documents - Not Chrome", "youtube")
        self.assertEqual(score, 0)

    def test_youtube_music_target_rejects_regular_youtube_title(self):
        score = score_window_title("Some Video - YouTube - Google Chrome", "youtube_music")
        self.assertEqual(score, 0)

    def test_youtube_target_rejects_youtube_music_title(self):
        score = score_window_title("YouTube Music - Google Chrome", "youtube")
        self.assertEqual(score, 0)


class SpotifyDeviceSelectionTests(unittest.TestCase):
    def test_prefers_named_device(self):
        devices = [
            {"name": "Living Room Speaker", "id": "1", "type": "Speaker", "is_active": False},
            {"name": "Office PC", "id": "2", "type": "Computer", "is_active": False},
        ]
        device = find_best_device(devices, "office")
        self.assertEqual(device["id"], "2")

    def test_prefers_computer_over_active_phone(self):
        # Computer-type is preferred over any active non-computer when no target given
        devices = [
            {"name": "Desktop", "id": "1", "type": "Computer", "is_active": False},
            {"name": "Phones", "id": "2", "type": "Smartphone", "is_active": True},
        ]
        device = find_best_device(devices, None)
        self.assertEqual(device["id"], "1")

    def test_prefers_active_computer(self):
        # When there are multiple computers, prefer the active one
        devices = [
            {"name": "Desktop", "id": "1", "type": "Computer", "is_active": False},
            {"name": "Laptop", "id": "2", "type": "Computer", "is_active": True},
        ]
        device = find_best_device(devices, None)
        self.assertEqual(device["id"], "2")


if __name__ == "__main__":
    unittest.main()
