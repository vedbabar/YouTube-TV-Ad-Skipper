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
the TV's session ever drops). Three common ways to keep it running 24/7:

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

### Option C: AWS EC2

Running it on a small cloud VM means nothing at home has to stay on. And
because the "Link with TV code" pairing is cloud-mediated -- it registers
your client through YouTube's servers, not via local-network discovery -- the
instance does **not** need to be on the same network as the TV. It can live
in any region.

1. **Launch an instance.** A `t3.micro` (or `t2.micro`) on the free tier is
   plenty: the script just holds a connection and waits, so CPU/RAM usage is
   negligible. Amazon Linux 2023 or Ubuntu both work fine.

2. **Security group.** The script only makes *outbound* connections to
   YouTube, so you don't need to open any inbound app ports. Allow inbound
   SSH (port 22) from your IP only, and keep the default "allow all
   outbound". (If you later add the optional FastAPI `/status` endpoint,
   open that port too -- ideally restricted to your own IP.)

3. **SSH in and set up.** Using a virtualenv keeps things clean and avoids
   the "externally-managed-environment" pip error on newer Ubuntu/Debian:
   ```bash
   # Amazon Linux 2023
   sudo dnf install -y python3 python3-pip git
   # Ubuntu: sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

   git clone <your-repo-url> youtube-ad-skipper
   cd youtube-ad-skipper
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

4. **Pair once (interactively).** Pairing needs the TV code typed in once, so
   run it by hand the first time to generate `auth.json`:
   ```bash
   .venv/bin/python skipper.py
   ```
   Open YouTube on the TV > Settings > "Link with TV code", paste the code,
   confirm it skips an ad, then Ctrl-C. (Alternatively, pair on your laptop
   and `scp auth.json` up to the instance.)

5. **Run it 24/7 with systemd.** Reuse the Option A unit file, adjusting
   `User`, `WorkingDirectory`, and the python path. On Amazon Linux the
   default user is `ec2-user`; point `ExecStart` at the venv's python:
   ```ini
   [Unit]
   Description=YouTube Ad Skipper
   After=network-online.target

   [Service]
   User=ec2-user
   WorkingDirectory=/home/ec2-user/youtube-ad-skipper
   ExecStart=/home/ec2-user/youtube-ad-skipper/.venv/bin/python skipper.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo cp ad-skipper.service /etc/systemd/system/
   sudo systemctl enable --now ad-skipper
   journalctl -u ad-skipper -f
   ```
   `enable` makes it survive instance reboots; `Restart=always` covers the
   script reconnecting if the TV session drops.

**Cost note:** outside the 12-month free tier a `t3.micro` runs a few dollars
a month, and since the instance only talks outbound you don't need an Elastic
IP or any inbound traffic. To go cheaper, the same steps work on a `t4g.nano`
(ARM/Graviton) -- the dependencies are pure Python, so the architecture
doesn't matter.

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
