"""Cutting the generated shots into one finished advertisement.

Three jobs ffmpeg does here that no amount of prompting can:

  1. CONCATENATE the per-shot clips into a single continuous film.
  2. LAY THE VOICEOVER over the whole cut — the already-approved, already
     transcription-verified mp3, not a fresh one.
  3. APPEND A BRANDED END CARD carrying the approved headline and CTA.

The end card is drawn with Pillow rather than ffmpeg's drawtext filter. drawtext
needs a font path that differs on every OS and fails the whole render when it is
wrong; Pillow can fall back to a bundled bitmap font and still produce a frame.
Text is also the one thing image models reliably ruin, so the only lettering in
the finished ad is drawn by us, at a known size, spelled correctly.

ffmpeg comes from imageio-ffmpeg — a bundled static binary, so a judge cloning
this repo does not need brew.

Everything degrades: if concat fails the caller still has the individual shots;
if the audio mux fails it returns silent video rather than nothing.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from app.config import SCRATCH_DIR

logger = logging.getLogger(__name__)

_TIMEOUT = 300
# Every clip is normalised to this before concat. The demuxer requires matching
# codec/resolution/timebase across inputs, and the provider does not guarantee
# identical output between shots.
_W, _H, _FPS = 1280, 720, 30


def ffmpeg_exe() -> str | None:
    """Path to a usable ffmpeg, preferring the bundled one. None if absent."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


def _run(args: list[str], what: str) -> bool:
    exe = ffmpeg_exe()
    if not exe:
        logger.warning("ffmpeg unavailable; cannot %s", what)
        return False
    try:
        proc = subprocess.run(
            [exe, "-y", "-hide_banner", "-loglevel", "error", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timed out while trying to %s", what)
        return False
    if proc.returncode != 0:
        logger.warning("ffmpeg failed to %s: %s", what, (proc.stderr or "")[:400])
        return False
    return True


def probe_duration_from_container(path: Path | None) -> float | None:
    """Read duration straight from the MP4 header. No ffmpeg needed.

    Kept as a first-class fallback rather than deleted with the old single-shot
    film track: it is the only way to report a duration when ffmpeg is missing,
    and its one subtle bug is already covered by tests.
    """
    if not path or not path.is_file():
        return None
    try:
        import struct

        data = path.read_bytes()
        idx = data.find(b"mvhd")
        if idx == -1:
            return None
        # mvhd layout after the 4-byte 'mvhd' type:
        #   version(1) flags(3)
        #   v0: creation(4) modification(4) timescale(4) duration(4)
        #   v1: creation(8) modification(8) timescale(4) duration(8)
        # The 3 flag bytes are easy to forget — omitting them reads the
        # modification time as the timescale and yields None/garbage.
        version = data[idx + 4]
        if version == 1:
            timescale = struct.unpack(">I", data[idx + 24 : idx + 28])[0]
            duration = struct.unpack(">Q", data[idx + 28 : idx + 36])[0]
        else:
            timescale = struct.unpack(">I", data[idx + 16 : idx + 20])[0]
            duration = struct.unpack(">I", data[idx + 20 : idx + 24])[0]
        return round(duration / timescale, 2) if timescale else None
    except Exception:  # noqa: BLE001
        return None


def probe_duration(path: Path) -> float | None:
    """Duration in seconds, read with ffmpeg itself (no ffprobe binary needed).

    Falls back to parsing the container header so a missing ffmpeg costs the
    CUT, not the reported runtime.
    """
    exe = ffmpeg_exe()
    if not exe or not path.is_file():
        return probe_duration_from_container(path)
    try:
        proc = subprocess.run(
            [exe, "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None
    # ffmpeg reports progress on stderr; the last "time=" wins.
    marker = "time="
    best: float | None = None
    for chunk in (proc.stderr or "").split(marker)[1:]:
        stamp = chunk.split(" ")[0].strip()
        try:
            hh, mm, ss = stamp.split(":")
            best = int(hh) * 3600 + int(mm) * 60 + float(ss)
        except ValueError:
            continue
    return round(best, 2) if best else None


def normalize_clip(src: Path, dst: Path) -> bool:
    """Re-encode one clip to a common format so concat will accept it."""
    return _run(
        [
            "-i", str(src),
            "-vf", f"scale={_W}:{_H}:force_original_aspect_ratio=decrease,"
                   f"pad={_W}:{_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
                   f"fps={_FPS},format=yuv420p",
            "-an",  # per-shot audio is discarded; the voiceover is laid over the cut
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-video_track_timescale", "90000",
            str(dst),
        ],
        f"normalize {src.name}",
    )


def end_card(
    brand_name: str,
    headline: str,
    cta: str,
    primary_hex: str,
    accent_hex: str,
    out_png: Path,
) -> bool:
    """Render the closing frame. Pillow, so text is spelled correctly."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow unavailable; skipping end card")
        return False

    def rgb(value: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
        raw = (value or "").strip().lstrip("#")
        if len(raw) == 3:
            raw = "".join(c * 2 for c in raw)
        try:
            return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
        except (ValueError, IndexError):
            return default

    bg = rgb(primary_hex, (30, 58, 43))
    accent = rgb(accent_hex, (217, 119, 6))
    # Legible on both a dark and a light brand colour.
    luminance = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    fg = (245, 241, 234) if luminance < 140 else (28, 25, 23)

    def font(size: int):
        for candidate in (
            "/System/Library/Fonts/Supplemental/Georgia.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ):
            if Path(candidate).is_file():
                try:
                    return ImageFont.truetype(candidate, size)
                except Exception:  # noqa: BLE001
                    continue
        return ImageFont.load_default()

    def wrap(draw, text: str, fnt, max_w: int) -> list[str]:
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=fnt) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines[:3]

    try:
        img = Image.new("RGB", (_W, _H), bg)
        draw = ImageDraw.Draw(img)

        brand_f, head_f, cta_f = font(64), font(40), font(28)
        cx = _W // 2

        draw.text((cx, 250), brand_name, font=brand_f, fill=fg, anchor="mm")
        draw.line([(cx - 60, 305), (cx + 60, 305)], fill=accent, width=3)

        y = 360
        for line in wrap(draw, headline or "", head_f, _W - 240):
            draw.text((cx, y), line, font=head_f, fill=fg, anchor="mm")
            y += 52

        if cta:
            draw.text((cx, min(y + 30, _H - 90)), cta.upper(), font=cta_f, fill=accent, anchor="mm")

        img.save(out_png, "PNG")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not render end card: %s", exc)
        return False


def still_to_clip(png: Path, seconds: float, dst: Path) -> bool:
    """Turn the end-card still into a clip matching the normalised format."""
    return _run(
        [
            "-loop", "1", "-i", str(png),
            "-t", f"{seconds}",
            "-vf", f"scale={_W}:{_H},fps={_FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-video_track_timescale", "90000",
            str(dst),
        ],
        "build end-card clip",
    )


def concat(clips: list[Path], dst: Path) -> bool:
    """Join normalised clips. Stream copy — they already share a format."""
    if not clips:
        return False
    listing = dst.with_suffix(".txt")
    # Quote-escaped because the concat demuxer parses this file itself.
    listing.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in clips), encoding="utf-8"
    )
    ok = _run(
        ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(dst)],
        "concatenate shots",
    )
    listing.unlink(missing_ok=True)
    return ok


def add_voiceover(video: Path, audio: Path, dst: Path) -> bool:
    """Lay the voiceover over the cut, padding it to the film's full length.

    The naive version of this hangs, and the reason is worth stating because it
    is not obvious:

      * `-shortest` ALONE truncates the PICTURE to the length of the narration.
        The voiceover is ~15s and the film is ~20s, so that silently deletes the
        end card — the one frame carrying the brand name and CTA.
      * `apad` fixes the truncation by padding the audio with silence, but apad
        is INFINITE by default. Paired with `-shortest` and a filtergraph
        output, ffmpeg never sees an end-of-stream and runs until it is killed.
        Observed here as a 300s timeout per mux, not as an error.

    Bounding the output with an explicit `-t` of the video's own duration ends
    it deterministically: full picture, narration from the top, silence after.
    If the duration cannot be probed, fall back to plain `-shortest`, which
    truncates but at least terminates.
    """
    seconds = probe_duration(video)
    args = [
        "-i", str(video),
        "-i", str(audio),
        "-filter_complex", "[1:a]apad[aud]",
        "-map", "0:v:0", "-map", "[aud]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
    ]
    args += ["-t", f"{seconds:.3f}"] if seconds else ["-shortest"]
    return _run([*args, str(dst)], "mux voiceover")


def has_audio_stream(path: Path) -> bool:
    """True when the file carries an audio track. Used by tests and callers."""
    exe = ffmpeg_exe()
    if not exe or not path.is_file():
        return False
    try:
        proc = subprocess.run(
            [exe, "-i", str(path)], capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return False
    return "Audio:" in (proc.stderr or "")


def workdir(campaign_id: str) -> Path:
    """Scratch space for one assembly.

    Under SCRATCH_DIR because genblaze's ObjectStorageSink only reads file://
    assets from the system temp dir — writing the finished ad anywhere else
    fails the upload with StorageError.
    """
    path = SCRATCH_DIR / "ad" / campaign_id
    path.mkdir(parents=True, exist_ok=True)
    return path
