# Rockbox Album Art Grabber

Fetch album cover art for music libraries. Extracts embedded artwork from audio files, falls back to Discogs API.

## What it does

1. Walks through music directory
2. For each album folder:
   - Checks for existing `cover.jpg` → skips if found
   - Tries to extract embedded art from MP3/M4A/AAC files
   - If no embedded art, searches Discogs for release
   - Downloads primary image, resizes to 500x500, saves as `cover.jpg`
3. Logs misses and offers interactive retry

## Supported formats

- MP3 (ID3 APIC frames)
- M4A (MP4 covr atom)
- AAC

## Requirements

- Python 3.7+
- See `requirements.txt`

## Getting started

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python app.py /path/to/music
```

Example:

```bash
python app.py ~/Music
```

## Output

- Creates `cover.jpg` in each album folder
- Writes misses to `misses.log`
- After run, shows summary and offers retry for failed albums

## Retry options

When misses occur, you can:

- `s` - Enter custom search terms
- `m` - Paste manual image URL
- `k` - Skip this album
- `q` - Quit retry loop

## Discogs rate limiting

Free API: 25 requests/minute. Script handles 429 responses automatically (waits 60s, retries up to 3x).

## Docker

```bash
docker build -t album-art-grabber .
docker run -v /path/to/music:/app/Music album-art-grabber
```