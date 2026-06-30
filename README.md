# YouTube Ad Skipper

Automatically skips skippable YouTube ads on your TV (Android TV / Google TV /
Chromecast / Fire TV) without installing anything on the TV itself.

## How it works

When you pair a phone as a remote with the YouTube app on your TV (Settings >
"Link with TV code"), you're not modifying the TV app -- you're registering a
second client on the same playback session via YouTube's "Lounge API", the
protocol behind casting and remote control. Any registered client can send
commands (play, pause, seek, skip ad) and receives live state updates,
including whether the skip button is currently enabled.

This script registers itself as exactly that kind of client, listens for
the `is_skip_enabled` flag on ad-state events, and fires the skip command
the instant it goes true -- faster than a human could reach for a remote.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. On your TV: open the YouTube app > Settings > "Link with TV code". Note
   the code shown (it stays valid for a few minutes).

3. Run the script:
   ```
   python skipper.py
   ```
   Paste the code when prompted. Once paired, it saves a `screen_id` to
   `auth.json` so you won't need to re-enter a code on future runs (only the
   short-lived session token gets refreshed automatically each run).

4. Play a video with a skippable ad on the TV and watch the terminal log --
   you should see it detect and skip the ad within a second of skipping
   becoming available.

Keep the script running in the background (it loops forever, reconnecting if
the TV's session ever drops). Two common ways to keep it running 24/7:

### Option A: systemd (Linux machine / Raspberry Pi)

Create `/etc/systemd/system/ad-skipper.service`:
```ini
[Unit]
Description=YouTube Ad Skipper
After=network-online.target

[Service]
WorkingDirectory=/home/pi/youtube-ad-skipper
ExecStart=/usr/bin/python3 skipper.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Then:
```
sudo systemctl enable --now ad-skipper
journalctl -u ad-skipper -f   # tail logs
```
Note the first run still needs to happen interactively (or pre-seed
`auth.json`) since pairing requires typing in the code once.

### Option B: Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY skipper.py .
CMD ["python", "skipper.py"]
```
Pair once locally first so `auth.json` exists, then mount it as a volume so
the container reuses it instead of needing an interactive prompt:
```
docker run -d --restart unless-stopped -v $(pwd)/auth.json:/app/auth.json ad-skipper
```

## Notes & gotchas

- The TV's YouTube app needs to actually be open (foreground or background)
  for the session to be connectable -- if the TV is fully off or YouTube was
  force-closed, `connect()` will fail until it's reopened. The script just
  retries with backoff in that case.
- This rides on an undocumented API. YouTube has occasionally changed the
  screen ID format, which revokes existing pairings -- if that happens
  you'll see pairing get rejected and the script will prompt for a fresh
  code automatically.
- This only affects your own client/session; it doesn't modify the YouTube
  app, block ads outright, or touch network traffic -- it just automates
  pressing a button that's already there for you to press.

## Ideas to extend it

- Add [SponsorBlock](https://sponsor.ajay.app/) integration to also skip
  in-video sponsor segments (this is what inspired the project --
  [iSponsorBlockTV](https://github.com/dmunozv04/iSponsorBlockTV) does this
  and is worth reading for more advanced patterns).
- Wrap this in a small FastAPI service exposing `/status` and `/pause` so you
  can monitor or control it from a browser.
- Support pairing multiple TVs/screens at once by running multiple
  `YtLoungeApi` instances concurrently.
