"""Unit tests untuk PiperTTS dan generator naskah DJ fallback."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.llm import LLMClient
from app.tts import PiperTTS, TTSError


def test_tts_and_fallback():
    # 1. Test TTS disabled / missing binary handling
    s = Settings(
        host_enabled=False,
        piper_path="bin/piper.exe",
        piper_model="models/id_ID-news-medium.onnx",
    )
    tts = PiperTTS(s)
    assert not tts.is_available()

    try:
        tts.synthesize("Halo pendengar radio!")
        assert False, "Should raise TTSError when disabled"
    except TTSError as e:
        assert "dinonaktifkan" in str(e).lower()

    # 2. Test LLM client DJ generator fallback when disabled (empty api key)
    s_llm = Settings(openrouter_api_key="")
    llm = LLMClient(s_llm)
    assert not llm.enabled

    script = asyncio.run(
        llm.generate_dj_script(
            current_title="Dan",
            current_artist="Sheila on 7",
            requested_by="Budi",
            shoutout_message="Salam buat anak kos",
        )
    )
    # When disabled, should cleanly return empty string without crash
    assert script == ""

    print("ALL TTS & DJ SCRIPT TESTS PASSED!")


if __name__ == "__main__":
    test_tts_and_fallback()
