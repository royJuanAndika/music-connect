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
        duck_level=0.03,
        duck_attack_ms=15,
        duck_release_ms=600,
    )
    engine = AudioEngine(s)

    # 1. Test filter string
    filt, map_hls, map_rtmp = engine.build_ducking_filter(output_hls=True, output_rtmp=True)
    assert "sidechaincompress=" in filt
    assert "apad" in filt
    assert "threshold=0.03" in filt
    assert "ratio=16" in filt
    assert map_hls == "[out_hls]"
    assert map_rtmp == "[out_rtmp]"

    # Test RTMP only mode (should not have asplit)
    filt_rtmp_only, _, map_rtmp_only = engine.build_ducking_filter(output_hls=False, output_rtmp=True)
    assert "asplit" not in filt_rtmp_only
    assert map_rtmp_only == "[out_rtmp]"
    assert "attack=15" in filt
    assert "release=600" in filt
    assert "amix=" in filt

    # 2. Test command generator dengan voice host + RTMP + HLS
    music_file = Path("data/tracks/dummy_music.opus")
    voice_file = Path("data/voice/dummy_voice.wav")
    # Touch dummy files for testing cmd generation
    voice_file.parent.mkdir(parents=True, exist_ok=True)
    voice_file.touch()

    # Case A: Both HLS and RTMP
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
    assert "-f fifo -fifo_format flv" in cmd_str
    assert "-drop_pkts_on_overflow 1" in cmd_str
    assert "rtmp://live.telegram.org/app/secretkey123" in cmd_str
    assert "-max_muxing_queue_size 9999" in cmd_str
    assert "-fps_mode cfr" in cmd_str
    assert "-maxrate 100k" in cmd_str
    assert "-bufsize 200k" in cmd_str
    assert "asplit=2[out_hls][out_rtmp]" in cmd_str

    # Case B: RTMP only (VPS mode) - should NOT have asplit
    cmd_rtmp_only = engine.build_ffmpeg_cmd(
        music_file=music_file,
        voice_file=voice_file,
        output_hls=False,
        output_rtmp=True,
    )
    cmd_rtmp_str = " ".join(cmd_rtmp_only)
    assert "asplit" not in cmd_rtmp_str
    assert "-map [out_rtmp]" in cmd_rtmp_str
    assert "-f hls" not in cmd_rtmp_str
    assert "-f fifo -fifo_format flv" in cmd_rtmp_str

    # Test standby command
    standby_cmd = engine.build_standby_cmd(10, output_hls=True, output_rtmp=True)
    standby_str = " ".join(standby_cmd)
    assert "anullsrc=" in standby_str
    assert "-f fifo -fifo_format flv" in standby_str
    assert "-maxrate 100k" in standby_str
    assert "-bufsize 200k" in standby_str

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
