"""
Saving and deleting photos.

Two jobs:
  1. process_image(): make an upload SAFE and SMALL
       - check it's genuinely an image (not a renamed .exe or a broken file)
       - rotate it the right way up (phones store rotation as a hidden tag)
       - shrink it to max 1200px, re-save as JPEG  -> ~150 KB instead of ~4 MB
       - re-saving drops all hidden "EXIF" data, including the GPS location
         where the photo was taken (which could reveal a student's home)
  2. save_image() / delete_image(): put the file somewhere and remember where.

WHY a separate file: right now photos go into a local "uploads/" folder.
When we go live, only THIS file changes (to upload to Cloudinary instead).
The rest of the app just calls save_image() and doesn't care where it goes.
"""
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import MAX_UPLOAD_MB, PUBLIC_BASE_URL, UPLOAD_DIR

MAX_SIDE_PX = 1200
# Refuse absurdly large images (a tiny file can claim to be 50,000 x 50,000 pixels
# and eat all the server's memory when opened - a "decompression bomb").
Image.MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO = what some phone cameras call their JPEGs


class BadImage(ValueError):
    """Raised with a user-friendly message when an upload isn't acceptable."""


def process_image(raw: bytes) -> bytes:
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise BadImage(f"Photo is too large. Maximum is {MAX_UPLOAD_MB} MB.")
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        img.load()  # actually decode it; broken files fail here
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise BadImage("That file isn't a valid image. Please upload a JPG, PNG or WEBP photo.")
    if fmt not in ALLOWED_FORMATS:
        raise BadImage("Unsupported image type. Please upload a JPG, PNG or WEBP photo.")

    img = ImageOps.exif_transpose(img)   # apply the phone's rotation tag
    img = img.convert("RGB")             # JPEG can't store transparency
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))  # shrink, keeping proportions

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)  # no exif passed -> stripped
    return out.getvalue()


# ---------- Local folder storage (used now) ----------
def _upload_dir() -> Path:
    path = Path(UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image(jpeg_bytes: bytes) -> tuple[str, str]:
    """Save the processed photo. Returns (url, storage_key)."""
    # Random file name: users can't guess other photos' names or overwrite them.
    key = f"{uuid.uuid4().hex}.jpg"
    (_upload_dir() / key).write_bytes(jpeg_bytes)
    return f"/uploads/{key}", key


def delete_image(storage_key: str) -> None:
    path = _upload_dir() / Path(storage_key).name  # .name blocks tricks like "../../secret"
    path.unlink(missing_ok=True)


def public_url(url: str) -> str:
    """Turn '/uploads/abc.jpg' into 'http://127.0.0.1:8000/uploads/abc.jpg'. Full URLs pass through."""
    return f"{PUBLIC_BASE_URL}{url}" if url.startswith("/") else url
