"""Unit test peracikan filter graph ducking, command HLS/RTMP, dan watchdog."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio_engine import AudioEngine
from app.config import Settings
from app.stream_watchdog import StreamWatchdog


def test_audio_engine():
    s = Settings(
        stream_mode="both",
        stream_bitrate="128k",
        rtmp_url="rtmp://live.telegram.org/app",
        rtmp_key="secretkey123",
        duck_level=0.25,
        duck_attack_ms=200,
        duck_release_ms=800,
    )
    engine = AudioEngine(s)

    # 1. Test filter string
    filt = engine.build_ducking_filter()
    assert "sidechaincompress=" in filt
    assert "threshold=0.25" in filt
    assert "attack=200" in filt
    assert "release=800" in filt
    assert "amix=" in filt

    # 2. Test command generator dengan voice host + RTMP + HLS
    music_file = Path("data/tracks/dummy_music.opus")
    voice_file = Path("data/voice/dummy_voice.wav")
    # Touch dummy files for testing cmd generation
    voice_file.parent.mkdir(parents=True, exist_ok=True)
    voice_file.touch()

    cmd = engine.build_ffmpeg_cmd(
        music_file=music_file,
        voice_file=voice_file,
        output_hls=True,
        output_rtmp=True,
    )

    cmd_str = " ".join(cmd)
    assert "-i " + str(music_file) in cmd_str
    assert "-i " + str(voice_file) in cmd_str
    assert "-filter_complex" in cmd_str
    assert "-f hls" in cmd_str
    assert "-f flv rtmp://live.telegram.org/app/secretkey123" in cmd_str

    if voice_file.exists():
        voice_file.unlink()

    # 3. Test Watchdog callback simulation
    crashed_handled = []
    notified = []

    async def mock_restart():
        crashed_handled.append(True)

    async def mock_notify(msg):
        notified.append(msg)

    watchdog = StreamWatchdog(
        restart_callback=mock_restart,
        notify_callback=mock_notify,
    )
    asyncio.run(watchdog.handle_crash("FFmpeg exit code 1"))

    assert len(crashed_handled) == 1
    assert len(notified) == 1
    assert "FFmpeg exit code 1" in notified[0]

    print("ALL AUDIO ENGINE & WATCHDOG TESTS PASSED!")


if __name__ == "__main__":
    test_audio_engine()
