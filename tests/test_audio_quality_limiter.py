from pathlib import Path
from app.config import Settings
from app.audio_engine import AudioEngine


def test_audio_config_defaults():
    s = Settings()
    assert s.stream_sample_rate == 48000
    assert s.stream_bitrate == "192k"
    assert s.duck_ratio == 5.0
    assert s.duck_attack_ms == 30
    assert s.duck_release_ms == 1200
    assert s.audio_limiter_enabled is True


def test_build_ducking_filter_contains_alimiter_and_vocal_filter():
    s = Settings(audio_limiter_enabled=True)
    engine = AudioEngine(s)
    filter_str, hls_map, rtmp_map = engine.build_ducking_filter(output_hls=True, output_rtmp=True)
    assert "alimiter=limit=0.95" in filter_str
    assert "highpass=f=80" in filter_str
    assert "ratio=5.0" in filter_str
    assert "asplit=2" in filter_str
    assert hls_map == "[out_hls]"
    assert rtmp_map == "[out_rtmp]"


def test_build_ducking_filter_limiter_disabled():
    s = Settings(audio_limiter_enabled=False)
    engine = AudioEngine(s)
    filter_str, _, _ = engine.build_ducking_filter(output_hls=True, output_rtmp=False)
    assert "alimiter" not in filter_str
    assert "highpass=f=80" in filter_str


def test_build_ffmpeg_cmd_parameters():
    s = Settings(
        stream_sample_rate=48000,
        stream_bitrate="192k",
        rtmp_url="rtmps://dc5-1.rtmp.t.me/s/",
        rtmp_key="12345:abcdef",
    )
    engine = AudioEngine(s)
    music = Path("dummy_music.opus")
    voice = Path("dummy_voice.mp3")

    cmd = engine.build_ffmpeg_cmd(
        music_file=music,
        voice_file=voice,
        output_hls=True,
        output_rtmp=True,
    )

    # Memastikan sample rate dan bitrate stereo 192k/48k terpasang
    assert "-ar" in cmd
    ar_indices = [i for i, x in enumerate(cmd) if x == "-ar"]
    for idx in ar_indices:
        assert cmd[idx + 1] == "48000"

    b_indices = [i for i, x in enumerate(cmd) if x == "-b:a"]
    for idx in b_indices:
        assert cmd[idx + 1] == "192k"


def test_build_message_cmd_parameters():
    s = Settings(
        stream_sample_rate=48000,
        stream_bitrate="192k",
        rtmp_url="rtmps://dc5-1.rtmp.t.me/s/",
        rtmp_key="12345:abcdef",
    )
    engine = AudioEngine(s)
    voice = Path("dummy_message.mp3")

    cmd = engine.build_message_cmd(
        voice_file=voice,
        output_hls=True,
        output_rtmp=True,
    )

    cmd_str = " ".join(cmd)
    assert "alimiter=limit=0.95" in cmd_str
    assert "highpass=f=80" in cmd_str
    assert "-ar 48000" in cmd_str
    assert "-b:a 192k" in cmd_str
