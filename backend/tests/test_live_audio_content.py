"""LIVE verification that the generated voiceover actually SAYS the script.

Checking that an ElevenLabs response is a well-formed MP3 proves almost
nothing — silence, a truncated buffer, or the wrong take would all pass. This
transcribes the real audio (fetched from Backblaze B2 through /api/media) with
an audio-capable model on TokenRouter and compares the words against the script
the pipeline generated.

Audible playback could not be confirmed in an automated browser (media elements
never load there — even a synthesized WAV control stalls), so this is the
strongest available evidence that the audio track is real and correct.

    uv run pytest tests/test_live_audio_content.py -m live -v -s
"""

from __future__ import annotations

import base64
import io
import math
import os
import re
import struct
import wave

import httpx
import pytest

pytestmark = pytest.mark.live

BASE = os.environ.get("FERNWOOD_TEST_BASE", "http://127.0.0.1:8787")
TR = "https://api.tokenrouter.com/v1"

# Audio-capable chat models (supported_endpoint_types == ["audio-chat"]).
# NOTE: /v1/audio/transcriptions is NOT usable — whisper-1 returns
# 503 model_not_found ("no available channel ... under group default").
TRANSCRIBE_MODELS = ["openai/gpt-audio-mini", "openai/gpt-audio"]


def _server_up() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


needs_server = pytest.mark.skipif(not _server_up(), reason="backend not running")


def _normalize(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()


@pytest.fixture(scope="module")
def voiceover():
    """The most recent real campaign that produced audio."""
    if not _server_up():
        pytest.skip("backend not running")
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        override=True,
    )
    campaigns = httpx.get(f"{BASE}/api/campaigns", timeout=30).json()["campaigns"]
    for c in campaigns:
        attempts = c.get("assets", {}).get("audio", {}).get("attempts", [])
        with_audio = [a for a in attempts if a["content"].get("audioUrl")]
        if with_audio:
            att = with_audio[-1]
            mp3 = httpx.get(f"{BASE}{att['content']['audioUrl']}", timeout=120).content
            return {
                "campaign_id": c["id"],
                "script": att["content"]["audioScript"],
                "mp3": mp3,
                "url": att["content"]["audioUrl"],
            }
    pytest.skip("no campaign with generated audio in the library")


@pytest.fixture(scope="module")
def transcript(voiceover) -> str:
    """Transcribe ONCE and share it.

    Transcription is non-deterministic and costs a call per invocation, so
    asserting against separate transcriptions made the suite flaky — a brand
    name that came back "Farnwood" in one call and "Hadburn Wood" in another
    failed a strict check while the audio itself was perfect.
    """
    api_key = os.environ["TOKENROUTER_API_KEY"]
    b64 = base64.b64encode(voiceover["mp3"]).decode()
    for model in TRANSCRIBE_MODELS:
        resp = httpx.post(
            f"{TR}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300,
            json={
                "model": model,
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Transcribe this audio verbatim. "
                                "Output only the words spoken.",
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {"data": b64, "format": "mp3"},
                            },
                        ],
                    }
                ],
            },
        )
        if resp.status_code < 400:
            text = resp.json()["choices"][0]["message"]["content"] or ""
            if text.strip():
                return text
    pytest.fail("no audio model returned a transcript")


@needs_server
class TestAudioIsRealSpeech:
    def test_transcription_matches_the_generated_script(self, voiceover):
        """The load-bearing assertion: the audio says what the script says."""
        api_key = os.environ["TOKENROUTER_API_KEY"]
        b64 = base64.b64encode(voiceover["mp3"]).decode()

        transcript = None
        for model in TRANSCRIBE_MODELS:
            resp = httpx.post(
                f"{TR}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=300,
                json={
                    "model": model,
                    "max_tokens": 500,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Transcribe this audio verbatim. "
                                    "Output only the words spoken.",
                                },
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": b64, "format": "mp3"},
                                },
                            ],
                        }
                    ],
                },
            )
            if resp.status_code < 400:
                text = resp.json()["choices"][0]["message"]["content"] or ""
                if text.strip():
                    transcript = text
                    break
        assert transcript, "no audio model returned a transcript"

        said = _normalize(transcript)
        expected = _normalize(voiceover["script"])
        assert said, "transcript was empty — the audio may be silent"

        overlap = len(set(said) & set(expected)) / max(1, len(set(expected)))
        print(f"\n  [live] script    : {voiceover['script'][:90]}...")
        print(f"  [live] transcript: {transcript.strip()[:90]}...")
        print(f"  [live] word overlap: {overlap:.0%}")

        # Word-for-word matches have been observed; 80% tolerates TTS eliding
        # punctuation or a transcriber's minor spelling choices.
        assert overlap >= 0.80, (
            f"transcript diverges from script (overlap {overlap:.0%})\n"
            f"script    : {voiceover['script']}\n"
            f"transcript: {transcript}"
        )

    def test_whole_script_was_spoken_not_just_the_opening(self, voiceover, transcript):
        """Guards truncation: a clip cut short transcribes only its first words.

        Deliberately checks the SCRIPT'S TAIL rather than the brand name —
        proper nouns get mis-heard phonetically ("Fernwood" came back as
        "Farnwood" and "Hadburn Wood" on different runs), so asserting on them
        tests the transcriber rather than our audio.
        """
        said = _normalize(transcript)
        expected = _normalize(voiceover["script"])
        assert len(said) >= 0.7 * len(expected), (
            f"transcript far shorter than script ({len(said)} vs {len(expected)} words) "
            "— audio may be truncated"
        )
        tail = [w for w in expected[-8:] if len(w) > 3]
        hits = sum(1 for w in tail if w in said)
        assert hits >= max(1, len(tail) // 2), (
            f"end of the script is missing from the audio; looked for {tail}"
        )

    def test_transcript_is_not_a_generic_take(self, voiceover, transcript):
        """Distinctive brief vocabulary must actually be audible."""
        said = set(_normalize(transcript))
        expected = _normalize(voiceover["script"])
        distinctive = [w for w in expected if len(w) > 5]
        if not distinctive:
            pytest.skip("script has no distinctive long tokens")
        hit_rate = sum(1 for w in distinctive if w in said) / len(distinctive)
        assert hit_rate >= 0.6, f"only {hit_rate:.0%} of distinctive words heard"


@needs_server
class TestAudioSignal:
    """Local checks needing no API call. mutagen parses MP3 frame headers, so
    no ffmpeg/system package is required."""

    def _info(self, mp3: bytes):
        from mutagen.mp3 import MP3

        return MP3(io.BytesIO(mp3)).info

    def test_decodes_as_a_real_mp3_stream(self, voiceover):
        info = self._info(voiceover["mp3"])
        print(
            f"\n  [live] {info.length:.1f}s  {info.bitrate // 1000}kbps  "
            f"{info.sample_rate}Hz  ch={info.channels}"
        )
        assert info.length > 0
        assert info.sample_rate >= 16000
        assert info.bitrate >= 64000

    def test_duration_is_plausible_for_the_script(self, voiceover):
        info = self._info(voiceover["mp3"])
        words = len(voiceover["script"].split())
        wps = words / info.length
        print(f"  [live] {words} words in {info.length:.1f}s = {wps:.2f} words/sec")
        assert 5 < info.length < 120, f"implausible duration {info.length:.1f}s"
        # Natural narration sits around 1.5-4.5 words/sec. A silent or truncated
        # file lands far outside that band.
        assert 0.8 < wps < 6.0, f"implausible speaking rate {wps:.2f} w/s"

    def test_byte_length_matches_declared_duration(self, voiceover):
        """Catches truncation: a cut-off file has far fewer bytes than its
        bitrate x duration implies."""
        info = self._info(voiceover["mp3"])
        expected = info.bitrate / 8 * info.length
        actual = len(voiceover["mp3"])
        ratio = actual / expected
        print(f"  [live] {actual:,}B vs ~{expected:,.0f}B expected ({ratio:.2f}x)")
        assert 0.75 < ratio < 1.35, f"size/duration mismatch ({ratio:.2f}x)"

    def test_pipeline_recorded_the_real_duration(self, voiceover):
        """durationSeconds must reach the UI, not fall back to a hardcoded
        default — this is what mutagen enables in ElevenLabsTTSProvider."""
        campaigns = httpx.get(f"{BASE}/api/campaigns", timeout=30).json()["campaigns"]
        campaign = next(c for c in campaigns if c["id"] == voiceover["campaign_id"])
        att = [
            a
            for a in campaign["assets"]["audio"]["attempts"]
            if a["content"].get("audioUrl")
        ][-1]
        recorded = att["content"].get("durationSeconds")
        if recorded is None:
            pytest.skip(
                "campaign generated before mutagen was installed; "
                "re-run a campaign to populate durationSeconds"
            )
        actual = self._info(voiceover["mp3"]).length
        assert abs(recorded - actual) < 1.5, (
            f"recorded {recorded}s vs actual {actual:.1f}s"
        )


@needs_server
class TestAudioDeliveryToTheBrowser:
    def test_served_same_origin_without_redirect(self, voiceover):
        """A cross-origin redirect is what stalled <audio> before."""
        r = httpx.get(f"{BASE}{voiceover['url']}", timeout=90, follow_redirects=False)
        assert r.status_code == 200, f"expected 200, got {r.status_code}"
        assert r.headers["content-type"].startswith("audio/")

    def test_range_request_supported(self, voiceover):
        r = httpx.get(
            f"{BASE}{voiceover['url']}", headers={"Range": "bytes=0-1023"}, timeout=60
        )
        assert r.status_code == 206
        assert len(r.content) == 1024
        assert r.headers["accept-ranges"] == "bytes"

    def test_bytes_match_what_was_stored(self, voiceover):
        """Two fetches must be byte-identical — no truncation or re-encoding."""
        again = httpx.get(f"{BASE}{voiceover['url']}", timeout=90).content
        assert again == voiceover["mp3"]
