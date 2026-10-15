"""Unit test & self-check untuk modul YouTubeDownloader."""
import sys
from pathlib import Path

# Insert root directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.downloader import DownloaderError, TrackMetadata, YouTubeDownloader


def test_validation():
    s = Settings(
        yt_max_duration_sec=600,
        yt_min_duration_sec=30,
        yt_block_live=True,
    )
    dl = YouTubeDownloader(s)

    # 1. Test live stream rejection
    live_meta = TrackMetadata(
        video_id="live1234567",
        title="Live Concert",
        uploader="Band",
        duration_sec=0,
        is_live=True,
        thumbnail_url="",
        webpage_url="https://youtube.com/watch?v=live1234567",
    )
    try:
        dl._validate_metadata(live_meta)
        assert False, "Should reject live stream"
    except DownloaderError as e:
        assert "live stream" in str(e).lower()

    # 2. Test max duration rejection
    long_meta = TrackMetadata(
        video_id="long1234567",
        title="1 Hour Podcast",
        uploader="Host",
        duration_sec=3600,
        is_live=False,
        thumbnail_url="",
        webpage_url="https://youtube.com/watch?v=long1234567",
    )
    try:
        dl._validate_metadata(long_meta)
        assert False, "Should reject long duration"
    except DownloaderError as e:
        assert "terlalu panjang" in str(e).lower()

    # 3. Test valid duration
    valid_meta = TrackMetadata(
        video_id="good1234567",
        title="Good Song",
        uploader="Artist",
        duration_sec=210,
        is_live=False,
        thumbnail_url="",
        webpage_url="https://youtube.com/watch?v=good1234567",
    )
    dl._validate_metadata(valid_meta)
    assert valid_meta.formatted_title == "Artist - Good Song"

    # 4. Test cache lookup
    cache_path = dl.get_cached_file("non_existent_id")
    assert cache_path is None

    print("ALL DOWNLOADER SELF-CHECKS PASSED!")


if __name__ == "__main__":
    test_validation()
