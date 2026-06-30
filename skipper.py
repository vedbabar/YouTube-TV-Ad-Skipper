"""
YouTube Ad Skipper
------------------
Uses YouTube's "Lounge API" -- the same protocol your phone uses when you
pair it as a remote with the YouTube app on your TV -- to watch for
skippable ads and skip them the instant skipping becomes available.

No app installed on the TV. This script just registers itself as a second
"remote" on your TV's existing YouTube session and sends a skip command
when the ad state says skipping is allowed.

First run:
    python skipper.py
    -> prompts for the pairing code shown on your TV at:
       YouTube app > Settings > Link with TV code

Every run after that reuses the saved screen_id (in auth.json) so you
don't need to re-enter the code.
"""

import asyncio
import json
import logging
import os
import sys

from pyytlounge import AdPlayingEvent, AdStateEvent, DisconnectedEvent, EventListener, YtLoungeApi

AUTH_FILE = "auth.json"
DEVICE_NAME = "Ad Skipper"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("skipper")


class SkipAdsListener(EventListener):
    """Reacts to ad-related events pushed from the TV's YouTube session."""

    def __init__(self, api: YtLoungeApi):
        super().__init__()
        self.api = api

    async def ad_state_changed(self, event: AdStateEvent) -> None:
        if event.is_skip_enabled:
            log.info("Skip became available -- skipping")
            await self.api.skip_ad()

    async def ad_playing_changed(self, event: AdPlayingEvent) -> None:
        log.info(
            "Ad started: %s (skippable=%s, skip_enabled=%s)",
            event.ad_title,
            event.is_skippable,
            event.is_skip_enabled,
        )
        if event.is_skip_enabled:
            await self.api.skip_ad()

    async def disconnected(self, event: DisconnectedEvent) -> None:
        log.warning("Disconnected from screen: %s", event.reason)


def load_screen_id() -> str | None:
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE) as f:
            return json.load(f).get("screen_id")
    return None


def save_screen_id(screen_id: str) -> None:
    with open(AUTH_FILE, "w") as f:
        json.dump({"screen_id": screen_id}, f)


async def link(api: YtLoungeApi) -> bool:
    """Pair using a saved screen_id if we have one, otherwise prompt for a
    fresh pairing code from the TV's YouTube > Settings > Link with TV code."""
    screen_id = load_screen_id()
    if screen_id:
        log.info("Found saved pairing, refreshing token...")
        try:
            if await api.pair_with_screen_id(screen_id):
                return True
        except Exception:
            log.warning("Saved pairing was rejected (revoked or expired) -- re-pairing")

    code = input("Enter the pairing code from YouTube > Settings > Link with TV code: ").strip()
    try:
        if not await api.pair(code):
            log.error("Pairing failed -- check the code and try again")
            return False
    except Exception:
        log.exception("Pairing request failed")
        return False

    save_screen_id(api.auth.screen_id)
    log.info("Paired with screen: %s", api.screen_name)
    return True


async def run() -> None:
    async with YtLoungeApi(DEVICE_NAME) as api:
        api.event_listener = SkipAdsListener(api)

        if not await link(api):
            sys.exit(1)

        backoff = 5
        while True:
            try:
                if not await api.connect():
                    log.warning("Could not connect -- is the TV on and YouTube open?")
                else:
                    log.info("Connected to %s -- watching for ads", api.screen_name)
                    backoff = 5
                    await api.subscribe()  # blocks here, dispatching events until disconnect
            except Exception:
                log.exception("Lost connection, retrying in %ss", backoff)

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(run())
