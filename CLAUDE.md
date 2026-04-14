# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python tool that fetches album cover art for music libraries. It walks through a music directory, extracts artist/album metadata from audio files, queries MusicBrainz for release IDs, and downloads cover art from the Cover Art Archive.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the tool (path is hardcoded in app.py)
python3 app.py

# Build Docker image
docker build -t album-art-grabber .

# Run in Docker
docker run -v /path/to/music:/app/Music album-art-grabber
```

## Architecture

Single-script architecture in `app.py`:

1. **`walk_root(root)`** - Walks directory tree, finds folders with audio files
2. **`process_album(folder)`** - Orchestrates cover art retrieval for one album
3. **`get_tags(audio_path)`** - Extracts artist/album from MP3/M4A/AAC using mutagen
4. **`search_musicbrainz(artist, album)`** - Queries MusicBrainz API for release ID
5. **`get_cover_url(release_id)`** - Fetches front cover URL from Cover Art Archive
6. **`save_cover(img_url, folder)`** - Downloads, resizes to 500x500, saves as `cover.jpg`

Key behaviors:
- Skips folders that already have `cover.jpg`
- Supports `.mp3`, `.m4a`, `.aac` audio formats
- Rate-limits with 1-second delay between saves (be polite to APIs)
- Hardcoded music root path in `__main__` block needs modification for different systems
- MusicBrainz API requires real email in `MB_HEADERS["User-Agent"]` per their rate-limiting policy