import os
import time
import sys
import requests
from io import BytesIO
from PIL import Image
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.aac import AAC

AUDIO_EXTS = {".mp3", ".m4a", ".aac"}

DISCOGS_HEADERS = {"User-Agent": "cover-fetcher/1.3 (you@example.com)"}

# Rate limiting: 25 requests per minute
DISCOGS_MIN_INTERVAL = 2.4  # seconds
last_discogs_request = 0

# Track misses
misses = []
LOG_FILE = "misses.log"


def log(msg):
    print(msg)
    sys.stdout.flush()


def record_miss(folder, reason, artist=None, album=None):
    entry = {"folder": folder, "reason": reason, "artist": artist, "album": album}
    misses.append(entry)
    with open(LOG_FILE, "a") as f:
        line = f"{folder}|{reason}|{artist or ''}|{album or ''}\n"
        f.write(line)


def extract_embedded_cover(audio_path):
    """Extract embedded album art from audio file. Returns PIL Image or None."""
    ext = os.path.splitext(audio_path.lower())[1]

    try:
        if ext == ".mp3":
            audio = MP3(audio_path, ID3=ID3)
            for tag in ["APIC:", "APIC"]:
                if tag in audio.tags:
                    for frame in audio.tags.getall(tag):
                        if frame.data:
                            return Image.open(BytesIO(frame.data)).convert("RGB")

        elif ext == ".m4a":
            audio = MP4(audio_path)
            if "covr" in audio.tags:
                covers = audio.tags["covr"]
                if covers:
                    return Image.open(BytesIO(covers[0])).convert("RGB")

        elif ext == ".aac":
            audio = AAC(audio_path)
            if audio.tags and "covr" in audio.tags:
                covers = audio.tags["covr"]
                if covers:
                    return Image.open(BytesIO(covers[0])).convert("RGB")

    except Exception as e:
        log(f"[WARN] embedded extraction failed: {e}")

    return None


def get_tags(audio_path):
    try:
        audio = MutagenFile(audio_path, easy=True)
        if not audio:
            return None, None
        artist = audio.get("artist", [None])[0]
        album = audio.get("album", [None])[0]
        return artist, album
    except Exception:
        return None, None


def discogs_rate_limit():
    """Ensure we don't exceed 25 requests per minute."""
    global last_discogs_request
    elapsed = time.time() - last_discogs_request
    if elapsed < DISCOGS_MIN_INTERVAL:
        time.sleep(DISCOGS_MIN_INTERVAL - elapsed)
    last_discogs_request = time.time()


def discogs_request(url, params=None, max_retries=3):
    """Make Discogs API request with 429 handling. Returns response or None."""
    for attempt in range(max_retries):
        discogs_rate_limit()

        try:
            r = requests.get(url, headers=DISCOGS_HEADERS, params=params, timeout=15)

            if r.status_code == 429:
                log(f"[429] rate limited, waiting 60s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(60)
                continue

            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            if r.status_code != 429:
                log(f"[ERR] Discogs request failed: {e}")
                return None
        except Exception as e:
            log(f"[ERR] Discogs request failed: {e}")
            return None

    log("[ERR] max retries exceeded")
    return None


def search_discogs(artist, album):
    """Search Discogs for release. Returns resource_url or None."""
    url = "https://api.discogs.com/database/search"
    params = {"q": f"{artist} {album}", "type": "release", "per_page": 1}

    r = discogs_request(url, params)
    if not r:
        return None

    try:
        data = r.json()
        if data.get("results"):
            return data["results"][0].get("resource_url")
    except Exception as e:
        log(f"[ERR] parse Discogs response: {e}")

    return None


def get_discogs_release(resource_url):
    """Get release details. Returns images array or None."""
    r = discogs_request(resource_url)
    if not r:
        return None

    try:
        data = r.json()
        return data.get("images")
    except Exception as e:
        log(f"[ERR] parse Discogs release: {e}")

    return None


def find_primary_image(images):
    """Find primary image in Discogs images array."""
    if not images:
        return None

    # Look for primary first
    for img in images:
        if img.get("type") == "primary":
            return img.get("uri")

    # Fall back to first image
    if images:
        return images[0].get("uri")

    return None


def save_cover(img, folder):
    """Save PIL Image as 500x500 cover.jpg."""
    img = img.resize((500, 500), Image.LANCZOS)
    out = os.path.join(folder, "cover.jpg")
    img.save(out, "JPEG", quality=90)


def save_cover_from_url(url, folder):
    """Download image from URL and save as cover.jpg."""
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, timeout=30, headers=headers)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    save_cover(img, folder)


def process_album(folder):
    cover_path = os.path.join(folder, "cover.jpg")
    if os.path.exists(cover_path):
        log(f"[SKIP] cover exists: {folder}")
        return

    files = os.listdir(folder)
    audio_files = [f for f in files if os.path.splitext(f.lower())[1] in AUDIO_EXTS]
    if not audio_files:
        return

    # Try embedded images first
    for audio_file in audio_files:
        audio_path = os.path.join(folder, audio_file)
        img = extract_embedded_cover(audio_path)
        if img:
            try:
                save_cover(img, folder)
                log(f"[OK] embedded cover saved from {audio_file}")
                return
            except Exception as e:
                log(f"[ERR] save embedded failed: {e}")
                continue

    # No embedded image found, try Discogs
    artist, album = get_tags(os.path.join(folder, audio_files[0]))
    if not artist or not album:
        log(f"[FAIL] no tags: {folder}")
        record_miss(folder, "no_tags")
        return

    log(f"[SCAN] {artist} / {album}")

    resource_url = search_discogs(artist, album)
    if not resource_url:
        log("[MISS] no Discogs match")
        record_miss(folder, "no_match", artist, album)
        return

    images = get_discogs_release(resource_url)
    if not images:
        log("[MISS] no Discogs images")
        record_miss(folder, "no_images", artist, album)
        return

    cover_url = find_primary_image(images)
    if not cover_url:
        log("[NOTIFY] Discogs images found but no primary/uri available")
        record_miss(folder, "no_primary", artist, album)
        return

    try:
        save_cover_from_url(cover_url, folder)
        log("[OK] cover.jpg saved from Discogs")
    except Exception as e:
        log(f"[ERR] save failed: {e}")
        record_miss(folder, f"save_failed:{e}", artist, album)


def walk_root(root):
    for dirpath, _, files in os.walk(root):
        if any(os.path.splitext(f.lower())[1] in AUDIO_EXTS for f in files):
            process_album(dirpath)


def show_misses():
    if not misses:
        log("No misses recorded.")
        return

    log(f"\n=== MISSES ({len(misses)}) ===")
    for i, m in enumerate(misses, 1):
        artist_album = f"{m['artist']} / {m['album']}" if m['artist'] else "no tags"
        log(f"{i}. [{m['reason']}] {artist_album} - {m['folder']}")


def retry_misses():
    """Retry misses with user input for manual search terms."""
    if not misses:
        return

    log("\n=== RETRY MISSES ===")
    for m in misses[:]:
        log(f"\nFolder: {m['folder']}")
        log(f"Artist/Album: {m['artist']} / {m['album']}")
        log(f"Reason: {m['reason']}")

        choice = input("Retry? (s=search terms / m=manual url / k=skip / q=quit): ").strip().lower()

        if choice == "q":
            break
        elif choice == "k":
            continue
        elif choice == "s":
            custom = input("Enter search terms: ").strip()
            if custom:
                resource_url = search_discogs(custom, "")
                if resource_url:
                    images = get_discogs_release(resource_url)
                    if images:
                        cover_url = find_primary_image(images)
                        if cover_url:
                            try:
                                save_cover_from_url(cover_url, m["folder"])
                                log("[OK] cover saved")
                                misses.remove(m)
                            except Exception as e:
                                log(f"[ERR] {e}")
                        else:
                            log("[FAIL] no primary image")
                    else:
                        log("[FAIL] no images")
                else:
                    log("[FAIL] no match")
        elif choice == "m":
            url = input("Enter image URL: ").strip()
            if url:
                try:
                    save_cover_from_url(url, m["folder"])
                    log("[OK] cover saved")
                    misses.remove(m)
                except Exception as e:
                    log(f"[ERR] {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python app.py <music-folder>")
        sys.exit(1)

    root = sys.argv[1]
    if not os.path.isdir(root):
        log(f"Error: '{root}' is not a valid directory")
        sys.exit(1)

    log(f"Root: {root}")
    walk_root(root)
    log("Done")

    show_misses()

    if misses:
        choice = input("\nRetry misses? (y/n): ").strip().lower()
        if choice == "y":
            retry_misses()

    log("\nFinal misses saved to misses.log")