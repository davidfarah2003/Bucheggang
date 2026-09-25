"""Record the user flow as a short ad-style video: agent chat on the left, the Wallet on the right.

The stage page app/demo-stage.html embeds the real Wallet in a phone frame next to a mirrored agent
chat, inside a camera layer that the script zooms like a screen recorder. The script drives the
Wallet while the real agent side runs as a subprocess (scripts/flow_sim.py --manual, over the real
MCP server, models on). Every agent wait returns when the customer acts on the phone, so the timing
you see is the real backend's. Taps and the four event sounds are synthesized by scripts/demo_audio.py
from the cue times this script records while it runs; the music bed is docs/demo/music/ (CC BY 4.0).

    uv run --group classifier --with playwright python scripts/record_demo.py

Writes docs/demo/leash-user-flow.mp4 and docs/demo/leash-user-flow.gif. Requires a Wallet on
http://127.0.0.1:8000 started by scripts/wallet.sh on a wiped data/.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:8000"
INSTRUCTION = ("Do the weekly grocery shopping online at supermarkets I already use. Never spend more than "
               "CHF 100 per order or CHF 250 in any 7-day window; groceries and household basics only. If unsure, ask.")
W, H = 1600, 900
FPS = 30
PHONE_CX = 1305   # centre x of the phone on the stage
MUSIC = ROOT / "docs" / "demo" / "music" / "wallpaper.mp3"   # Kevin MacLeod, CC BY 4.0, credit in docs/demo/music/README.md
MUSIC_GAIN = 0.15


class Stage:
    def __init__(self, page):
        self.page = page
        self.frame = None
        self.t0 = time.monotonic()
        self.cues: list[dict] = []

    def cue(self, kind: str):
        self.cues.append({"t": round(time.monotonic() - self.t0, 3), "kind": kind})

    async def say(self, kind: str, html: str, hold: float = 0.9):
        await self.page.evaluate("([k,h]) => window.say(k,h)", [kind, html])
        await asyncio.sleep(hold)

    async def tool(self, name: str, args: str, hold: float = 0.6):
        await self.page.evaluate("([n,a]) => window.tool(n,a)", [name, args])
        await asyncio.sleep(hold)

    async def done(self, hold: float = 0.4, sound: str | None = None):
        # Silent by default. Only the four events that change something for Alex get a sound.
        await self.page.evaluate("() => window.done()")
        if sound:
            self.cue(sound)
        await asyncio.sleep(hold)

    async def caption(self, text: str, hold: float = 0.8, side: bool = False):
        await self.page.evaluate("([t,s]) => window.caption(t,s)", [text, side])
        await asyncio.sleep(hold)

    async def zoom(self, x: float, y: float, s: float, ms: int = 900, hold: float | None = None, cx: float = 800):
        # Camera moves are silent.
        await self.page.evaluate("([x,y,s,ms,cx]) => window.zoom(x,y,s,ms,cx)", [x, y, s, ms, cx])
        await asyncio.sleep(ms / 1000 if hold is None else hold)

    async def zoom_out(self, ms: int = 800):
        await self.zoom(800, 450, 1, ms)

    async def _point(self, selector: str):
        """Stage coordinates (inside the camera) of a Wallet element."""
        el = self.frame.locator(selector).first
        await el.scroll_into_view_if_needed()
        # The stage page must never scroll; a zoomed phone would otherwise drag the whole composition.
        await self.page.evaluate("() => window.scrollTo(0, 0)")
        await asyncio.sleep(0.08)
        box = await el.bounding_box()
        if box is None:
            raise RuntimeError(f"no box for {selector}")
        # The iframe's client rect is in viewport pixels and already includes the camera zoom.
        r = await self.page.evaluate("() => { const r = document.querySelector('#wallet').getBoundingClientRect(); return [r.left, r.top, r.width / 430]; }")
        vx = r[0] + (box["x"] + box["width"] / 2) * r[2]
        vy = r[1] + (box["y"] + min(box["height"] / 2, 40)) * r[2]
        sx, sy = await self.page.evaluate("([x,y]) => window.toStage(x,y)", [vx, vy])
        return sx, sy

    async def click(self, selector: str, after: float = 0.6):
        x, y = await self._point(selector)
        await self.page.evaluate("([x,y]) => window.cursor(x,y,false)", [x, y])
        await asyncio.sleep(0.3)
        await self.page.evaluate("([x,y]) => window.cursor(x,y,true)", [x, y])
        self.cue("tap")
        await asyncio.sleep(0.12)
        await self.frame.locator(selector).first.click()
        await self.page.evaluate("([x,y]) => window.cursor(x,y,false)", [x, y])
        await asyncio.sleep(after)

    async def type_into(self, selector: str, text: str, per_char: float = 0.018):
        await self.click(selector, after=0.2)
        await self.frame.locator(selector).first.type(text, delay=int(per_char * 1000))
        await asyncio.sleep(0.15)

    async def scroll(self, dy: int, steps: int = 16):
        # Wheel over the phone's viewport position; the iframe scrolls whatever is under the mouse.
        r = await self.page.evaluate("() => { const r = document.querySelector('#wallet').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
        await self.page.mouse.move(r[0], r[1])
        for _ in range(steps):
            await self.page.mouse.wheel(0, dy / steps)
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.25)


async def wait_for_agent(log: Path, needle: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while not (log.exists() and needle in log.read_text()):
        if time.monotonic() > deadline:
            raise TimeoutError(f"agent never logged {needle!r}; see {log}")
        await asyncio.sleep(0.1)


async def main() -> None:
    out = ROOT / "docs" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    work = ROOT / ".cotal" / "gif"
    video_dir = work / "video"
    shutil.rmtree(video_dir, ignore_errors=True)
    video_dir.mkdir(parents=True)
    log = work / "agent.log"
    log.unlink(missing_ok=True)

    agent = subprocess.Popen(
        ["uv", "run", "--group", "classifier", "python", str(ROOT / "scripts" / "flow_sim.py"), "--manual"],
        cwd=ROOT, env={**os.environ}, stdout=log.open("w"), stderr=subprocess.STDOUT,
    )
    s: Stage | None = None
    record_started = 0.0
    try:
        # The agent boots the MCP server and the models before any frame is recorded; its connect
        # call then sits pending in the Wallet until Alex opens the tab.
        await wait_for_agent(log, "connection request is waiting")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(
                viewport={"width": W, "height": H}, device_scale_factor=1,
                record_video_dir=str(video_dir), record_video_size={"width": W, "height": H},
            )
            record_started = time.monotonic()
            page = await context.new_page()
            await page.goto(f"{ORIGIN}/app/demo-stage.html")
            frame = page.frame(name="wallet") or next(f for f in page.frames if f.url.endswith("/app/"))
            await frame.wait_for_selector('[data-action="auth-mode"]')
            # Alex's account is created through the Wallet API in the browser's own session, so the
            # video opens on the Shop screen instead of a sign-up form.
            await frame.evaluate("""async () => {
                const r = await fetch('/account', { method: 'POST', headers: { 'content-type': 'application/json' },
                    body: JSON.stringify({ username: 'alex', password: 'demo-password-1' }) });
                if (!r.ok) throw new Error('register failed ' + r.status);
                location.reload();
            }""")
            frame = page.frame(name="wallet") or next(f for f in page.frames if f.url.endswith("/app/"))
            await frame.wait_for_selector("#shop-prompt")
            await asyncio.sleep(0.3)
            s = Stage(page)
            s.frame = frame
            await page.evaluate("() => window.scene('title')")
            await asyncio.sleep(1.0)
            await page.evaluate("() => window.scene('stage')")
            await page.evaluate("() => window.scene('lead', 'Alex sets the rules first.', 'One sentence, before anything is bought.')")
            await s.zoom(PHONE_CX, 480, 1.35, 600, hold=0.5)
            await s.type_into("#shop-prompt", INSTRUCTION, per_char=0.0015)

            # The MCP beat: any agent can plug in, and it does the rest.
            await s.zoom_out(500)
            await page.evaluate("() => window.scene('chips', 'Any agent does the rest.', 'The Wallet is an MCP server. The agent connects, drafts the plan and waits for Alex.')")
            await asyncio.sleep(1.5)
            await page.evaluate("() => window.scene('agent')")
            await s.say("user", INSTRUCTION, 0.2)
            await s.say("agent", "On it. Asking your Wallet for permission.", 0.15)
            await s.tool("connect", 'agent_label="Grocery helper"', 0.15)
            await s.caption("One tap to connect.", 0.4)
            await s.click('nav [data-route="wallet"]', after=0.15)
            await s.frame.wait_for_selector('[data-action="approve-pending-pair"]')
            await s.zoom(PHONE_CX, 420, 1.5, 450, hold=0.15)
            await s.click('[data-action="approve-pending-pair"]', after=0.15)
            await s.zoom_out(400)
            await s.done(0.15, sound="connect")
            await s.say("agent", "Connected. Turning your sentence into a spending plan.", 0.15)
            await s.tool("propose_task_policy", "instruction, proposal{6 rules, 1 question}")
            await wait_for_agent(log, "policy proposed")
            await s.done(0.1)
            await s.tool("wait_for_policy", "draft_id", 0.15)
            await s.caption("The agent drafted the plan. Only Alex can authorize it.", 0.4)
            await s.frame.wait_for_selector('[data-action="open-draft"]', timeout=15000)
            await s.click('[data-action="open-draft"]', after=0.25)
            await s.zoom(PHONE_CX, 470, 1.45, 500, hold=0.15)
            await s.caption("Plain-English rules, in Alex's words. Confirmed before the first purchase.", 0.6, side=True)
            await s.scroll(720, steps=8)
            await s.click('[data-action="answer-question"]', after=0.2)
            await s.click('[data-action="confirm"]', after=0.25)
            await s.zoom_out(400)
            await wait_for_agent(log, "policy confirmed")
            await s.done(0.25, sound="confirm")
            await s.caption("Rules confirmed. The agent shops inside them.", 0.5)
            await s.say("agent", "Confirmed. Ordering the weekly basket at Alpine Basket, CHF 35.00.", 0.15)
            await s.tool("buy", "mandate_id, cart[1], merchant=Alpine Basket, total_chf=35.0, facts[1]")

            await wait_for_agent(log, "agent: buy ->")
            await s.done(0.1)
            await s.say("agent", "The Wallet wants your word on this one.", 0.1)
            await s.tool("wait_for_purchase", "authorization_id", 0.15)
            await s.click('[data-action="wallet-tab"][data-tab="needs"]', after=0.15)
            await s.frame.wait_for_selector('[data-action="open-pending"]', timeout=15000)
            await s.click('[data-action="open-pending"]', after=0.25)
            await s.zoom(PHONE_CX, 470, 1.5, 500, hold=0.15)
            await s.caption("Why it asks: a new device and a risk-model flag. The answer comes from Alex.", 1.6, side=True)
            await s.click('[data-action="resolve"][data-decision="approve"]', after=0.15)
            await s.zoom_out(400)
            await wait_for_agent(log, "customer answered")
            await s.done(0.4, sound="approve")
            await s.say("agent", "Approved. Trying a second shop for the missing items.", 0.15)
            await s.tool("buy", "mandate_id, merchant=Fresh Corner Market, total_chf=35.0")
            await wait_for_agent(log, "agent: done")
            await s.done(0.1)
            s.cue("deny")
            await s.say("agent", "Declined: shops you already use only, and this card has never bought there.", 0.7)

            # Why: the decision pipeline and the live probabilities, with the explainer on the left.
            await s.caption("Every decision on record, with the reason.", 0.3)
            await s.click('nav [data-route="activity"]', after=0.2)
            await s.frame.wait_for_selector('[data-action="open-detail"]')
            await s.click('[data-action="open-detail"] >> nth=1', after=0.25)
            await s.click('[data-action="inspector"][data-tab="summary"]', after=0.2)
            await s.click('[data-action="inspector"][data-tab="pipeline"]', after=0.15)
            await s.caption("", 0.0)
            await page.evaluate("() => window.scene('tech', 'How the Wallet judges a cart.')")
            await s.zoom(PHONE_CX, 470, 1.6, 500, hold=0.15, cx=1150)
            await s.scroll(900, steps=8)
            await asyncio.sleep(1.8)
            await s.zoom(PHONE_CX, 560, 1.9, 600, hold=0.15, cx=1150)
            await s.scroll(520, steps=6)
            await asyncio.sleep(2.0)
            await s.zoom_out(500)
            await page.evaluate("() => window.hideCursor()")
            s.cue("swell")
            await page.evaluate("() => window.scene('outro', 'Agent on a Leash', 'Your agent buys. Your Wallet decides.')")
            await asyncio.sleep(1.4)
            await context.close()
            await browser.close()
    finally:
        if agent.poll() is None:
            agent.terminate()

    videos = list(video_dir.glob("*.webm"))
    if len(videos) != 1:
        raise RuntimeError(f"expected one recording, found {videos}")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(videos[0])],
                           capture_output=True, text=True, check=True).stdout.strip()
    seconds = float(probe)
    if s is None:
        raise RuntimeError("stage never started")
    # The recording clock starts at the context, the stage clock at the first cue; shift cues onto the video.
    lead = s.t0 - record_started
    cues = [{"t": max(0.0, c["t"] + lead), "kind": c["kind"]} for c in s.cues]
    cues_file = work / "cues.json"
    cues_file.write_text(json.dumps(cues))
    audio = work / "audio.wav"
    subprocess.run(["uv", "run", "python", str(ROOT / "scripts" / "demo_audio.py"), f"{seconds:.3f}", str(cues_file), str(audio)],
                   cwd=ROOT, check=True)
    mp4 = out / "leash-user-flow.mp4"
    fade_out = max(0.0, seconds - 2.5)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(videos[0]), "-i", str(audio), "-i", str(MUSIC),
                    "-filter_complex",
                    f"[2:a]atrim=0:{seconds:.3f},volume={MUSIC_GAIN},afade=t=in:d=1.2,afade=t=out:st={fade_out:.3f}:d=2.5[m];"
                    f"[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]",
                    "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    gif = out / "leash-user-flow.gif"
    palette = video_dir / "palette.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp4), "-vf",
                    "fps=15,scale=1280:-1:flags=lanczos,palettegen=max_colors=256:stats_mode=diff", str(palette)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp4), "-i", str(palette), "-lavfi",
                    "fps=15,scale=1280:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
                    str(gif)], check=True)
    print(f"mp4: {mp4} {mp4.stat().st_size // 1024} KB, {seconds:.0f} s, {len(cues)} sound cues")
    print(f"gif: {gif} {gif.stat().st_size // 1024} KB")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
