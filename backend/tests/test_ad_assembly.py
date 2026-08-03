"""Advertisement assembly — the ffmpeg path, exercised for real.

These build synthetic clips with ffmpeg rather than mocking it, because every
bug this code can have is a bug in what ffmpeg actually does with real files:
mismatched timebases silently dropping shots at concat, `-shortest` truncating
the picture to the narration, an end card that renders blank. A mocked
subprocess would assert only that we composed the argv we meant to.

No network and no generation quota — synthetic colour bars stand in for the
generated shots.
"""

from __future__ import annotations

import subprocess

import pytest

from app.pipeline import assemble

ffmpeg = assemble.ffmpeg_exe()
needs_ffmpeg = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg unavailable")


def make_clip(path, seconds=2, color="red", size="640x360", fps=25):
    """A synthetic 'generated shot'.

    Deliberately NOT the normalised size/fps, so the tests prove that
    normalize_clip is what makes concat work rather than luck.
    """
    subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={seconds}:r={fps}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def make_audio(path, seconds=3):
    subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:a", "libmp3lame", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@needs_ffmpeg
def test_ffmpeg_is_bundled_not_a_system_dependency():
    """A judge cloning this repo must not need brew install ffmpeg."""
    assert "imageio_ffmpeg" in ffmpeg or "site-packages" in ffmpeg


@needs_ffmpeg
def test_probe_duration_reads_a_real_file(tmp_path):
    clip = make_clip(tmp_path / "a.mp4", seconds=3)
    assert 2.5 <= (assemble.probe_duration(clip) or 0) <= 3.5


@needs_ffmpeg
def test_normalize_makes_mismatched_clips_concatenable(tmp_path):
    """The provider does not guarantee identical output between shots.

    Concat's demuxer needs matching codec/resolution/timebase, so without
    normalisation a differently-sized second shot is silently dropped.
    """
    a = make_clip(tmp_path / "a.mp4", seconds=2, color="red", size="640x360", fps=25)
    b = make_clip(tmp_path / "b.mp4", seconds=2, color="blue", size="1024x576", fps=24)

    na, nb = tmp_path / "na.mp4", tmp_path / "nb.mp4"
    assert assemble.normalize_clip(a, na)
    assert assemble.normalize_clip(b, nb)

    out = tmp_path / "cut.mp4"
    assert assemble.concat([na, nb], out)

    # Both shots survived: the cut is the SUM of the parts, not just one of them.
    assert 3.5 <= (assemble.probe_duration(out) or 0) <= 4.6


@needs_ffmpeg
def test_concat_preserves_every_shot(tmp_path):
    """A dropped shot is the failure mode that makes an ad look like a clip."""
    clips = []
    for i, color in enumerate(("red", "green", "blue")):
        raw = make_clip(tmp_path / f"raw{i}.mp4", seconds=2, color=color)
        norm = tmp_path / f"n{i}.mp4"
        assert assemble.normalize_clip(raw, norm)
        clips.append(norm)

    out = tmp_path / "cut.mp4"
    assert assemble.concat(clips, out)
    assert 5.4 <= (assemble.probe_duration(out) or 0) <= 6.6  # 3 x 2s


@needs_ffmpeg
def test_concat_leaves_no_temp_listing_behind(tmp_path):
    clip = tmp_path / "n.mp4"
    assemble.normalize_clip(make_clip(tmp_path / "r.mp4"), clip)
    out = tmp_path / "cut.mp4"
    assemble.concat([clip], out)
    assert not out.with_suffix(".txt").exists()


@needs_ffmpeg
def test_concat_of_nothing_fails_cleanly(tmp_path):
    assert assemble.concat([], tmp_path / "x.mp4") is False


@needs_ffmpeg
def test_voiceover_is_muxed_without_truncating_the_picture(tmp_path):
    """The bug `apad` exists to prevent.

    With `-shortest` alone, a 3s narration over a 6s film truncates the FILM to
    3s — silently deleting the end card. The audio must be padded to the
    picture, never the other way round.
    """
    clip = tmp_path / "n.mp4"
    assert assemble.normalize_clip(make_clip(tmp_path / "r.mp4", seconds=6), clip)
    audio = make_audio(tmp_path / "vo.mp3", seconds=2)

    out = tmp_path / "final.mp4"
    assert assemble.add_voiceover(clip, audio, out)

    assert assemble.has_audio_stream(out)
    # Full 6s of picture survives the 2s narration.
    assert 5.4 <= (assemble.probe_duration(out) or 0) <= 6.6


@needs_ffmpeg
def test_muxed_output_actually_carries_audio(tmp_path):
    clip = tmp_path / "n.mp4"
    assemble.normalize_clip(make_clip(tmp_path / "r.mp4", seconds=3), clip)
    assert assemble.has_audio_stream(clip) is False  # normalize strips per-shot audio

    out = tmp_path / "final.mp4"
    assemble.add_voiceover(clip, make_audio(tmp_path / "vo.mp3", 3), out)
    assert assemble.has_audio_stream(out) is True


@needs_ffmpeg
def test_end_card_renders_with_brand_text(tmp_path):
    png = tmp_path / "card.png"
    assert assemble.end_card(
        brand_name="Fernwood Coffee",
        headline="The hour that isn't spoken for",
        cta="Start your first bag",
        primary_hex="#1E3A2B",
        accent_hex="#D97706",
        out_png=png,
    )
    assert png.is_file() and png.stat().st_size > 2000

    from PIL import Image

    with Image.open(png) as img:
        assert img.size == (1280, 720)
        # Not a blank fill: the text and rule must have marked the frame.
        assert len(img.convert("RGB").getcolors(maxcolors=100000) or []) > 3


@pytest.mark.parametrize("primary", ["#1E3A2B", "#F9F7F2"])
def test_end_card_text_stays_legible_on_dark_and_light_brands(tmp_path, primary):
    """Foreground is chosen by luminance, so a pale brand must not go white-on-white."""
    png = tmp_path / f"card-{primary.strip('#')}.png"
    assert assemble.end_card(
        brand_name="Fernwood",
        headline="A headline",
        cta="Buy now",
        primary_hex=primary,
        accent_hex="#D97706",
        out_png=png,
    )
    from PIL import Image

    with Image.open(png) as img:
        rgb = img.convert("RGB")
        bg = rgb.getpixel((5, 5))
        centre_band = [rgb.getpixel((x, 250)) for x in range(400, 880, 8)]
        # Some pixel in the brand-name band must differ from the background.
        assert any(abs(sum(p) - sum(bg)) > 90 for p in centre_band)


def test_end_card_survives_a_malformed_brand_colour(tmp_path):
    """Colours come from user input; a bad hex must not fail the whole film."""
    png = tmp_path / "card.png"
    assert assemble.end_card(
        brand_name="Brand",
        headline="Headline",
        cta="CTA",
        primary_hex="not-a-colour",
        accent_hex="",
        out_png=png,
    )
    assert png.is_file()


@needs_ffmpeg
def test_still_becomes_a_clip_of_the_requested_length(tmp_path):
    png = tmp_path / "card.png"
    assemble.end_card("B", "H", "C", "#1E3A2B", "#D97706", png)
    clip = tmp_path / "card.mp4"
    assert assemble.still_to_clip(png, 2.5, clip)
    assert 2.0 <= (assemble.probe_duration(clip) or 0) <= 3.0


@needs_ffmpeg
def test_end_card_concatenates_onto_the_film(tmp_path):
    """End-to-end shape of a finished ad: shots + card + narration."""
    shots = []
    for i, color in enumerate(("red", "green")):
        norm = tmp_path / f"n{i}.mp4"
        assemble.normalize_clip(make_clip(tmp_path / f"r{i}.mp4", seconds=2, color=color), norm)
        shots.append(norm)

    png = tmp_path / "card.png"
    assemble.end_card("Fernwood", "Headline here", "Buy now", "#1E3A2B", "#D97706", png)
    card = tmp_path / "card.mp4"
    assert assemble.still_to_clip(png, 2.0, card)
    shots.append(card)

    cut = tmp_path / "cut.mp4"
    assert assemble.concat(shots, cut)

    final = tmp_path / "final.mp4"
    assert assemble.add_voiceover(cut, make_audio(tmp_path / "vo.mp3", 3), final)

    assert 5.4 <= (assemble.probe_duration(final) or 0) <= 6.6  # 2 + 2 + 2
    assert assemble.has_audio_stream(final)


def test_missing_ffmpeg_degrades_instead_of_raising(tmp_path, monkeypatch):
    """No ffmpeg must cost the CUT, not the campaign."""
    monkeypatch.setattr(assemble, "ffmpeg_exe", lambda: None)
    assert assemble.concat([tmp_path / "a.mp4"], tmp_path / "o.mp4") is False
    assert assemble.add_voiceover(tmp_path / "a.mp4", tmp_path / "b.mp3", tmp_path / "o.mp4") is False
    assert assemble.probe_duration(tmp_path / "a.mp4") is None
    assert assemble.has_audio_stream(tmp_path / "a.mp4") is False


@needs_ffmpeg
def test_corrupt_input_fails_without_raising(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"this is not a video")
    assert assemble.normalize_clip(bad, tmp_path / "out.mp4") is False


def test_workdir_lives_under_the_sink_readable_root():
    """ObjectStorageSink only reads file:// assets from the system temp dir."""
    import tempfile

    path = assemble.workdir("camp-test")
    assert path.is_dir()
    assert str(path).startswith(tempfile.gettempdir())
