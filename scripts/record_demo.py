"""Record the user flow as a short ad-style video: agent chat on the left, the Wallet on the right.

The stage page app/demo-stage.html embeds the real Wallet in a phone frame. This script drives
the Wallet inside that frame while the real agent side runs as a subprocess
(scripts/flow_sim.py --manual, over the real MCP server, models on). Every agent wait returns
when the customer acts on the phone, so the timing you see is the real backend's. The left
panel mirrors the agent's log lines as chat bubbles and tool calls.

    uv run --group classifier --with playwright python scripts/record_demo.py

Writes docs/demo/leash-user-flow.mp4 and docs/demo/leash-user-flow.gif. Requires a Wallet on
http://127.0.0.1:8000 started by scripts/wallet.sh on a wiped data/.
"""

from __future__ import annotations

import asyncio
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


class Stage:
    def __init__(self, page):
        self.page = page
        self.frame = None

    async def say(self, kind: str, html: str, hold: float = 0.9):
        await self.page.evaluate("([k,h]) => window.say(k,h)", [kind, html])
        await asyncio.sleep(hold)

    async def tool(self, name: str, args: str, hold: float = 0.6):
        await self.page.evaluate("([n,a]) => window.tool(n,a)", [name, args])
        await asyncio.sleep(hold)

    async def done(self, hold: float = 0.4):
        await self.page.evaluate("() => window.done()")
        await asyncio.sleep(hold)

    async def caption(self, text: str, hold: float = 0.8):
        await self.page.evaluate("(t) => window.caption(t)", text)
        await asyncio.sleep(hold)

    async def _point(self, selector: str):
        el = self.frame.locator(selector).first
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(0.15)
        box = await el.bounding_box()
        if box is None:
            raise RuntimeError(f"no box for {selector}")
        # Map the iframe's own coordinates into the stage page (phone is scaled 0.82 at its origin).
        origin = await self.page.evaluate("() => { const r = document.querySelector('#wallet').getBoundingClientRect(); return [r.left, r.top, r.width / 430]; }")
        x = origin[0] + (box["x"] + box["width"] / 2) * origin[2]
        y = origin[1] + (box["y"] + min(box["height"] / 2, 40)) * origin[2]
        return x, y

    async def click(self, selector: str, after: float = 0.6):
        x, y = await self._point(selector)
        await self.page.evaluate("([x,y]) => window.cursor(x,y,false)", [x, y])
        await asyncio.sleep(0.45)
        await self.page.evaluate("([x,y]) => window.cursor(x,y,true)", [x, y])
        await asyncio.sleep(0.12)
        await self.frame.locator(selector).first.click()
        await self.page.evaluate("([x,y]) => window.cursor(x,y,false)", [x, y])
        await asyncio.sleep(after)

    async def type_into(self, selector: str, text: str, per_char: float = 0.018):
        await self.click(selector, after=0.2)
        await self.frame.locator(selector).first.type(text, delay=int(per_char * 1000))
        await asyncio.sleep(0.3)

    async def scroll(self, dy: int, steps: int = 16):
        x, y = await self._point("body")
        await self.page.mouse.move(x, y)
        for _ in range(steps):
            await self.page.mouse.wheel(0, dy / steps)
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.4)


async def wait_for_agent(log: Path, needle: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while not (log.exists() and needle in log.read_text()):
        if time.monotonic() > deadline:
            raise TimeoutError(f"agent never logged {needle!r}; see {log}")
        await asyncio.sleep(0.25)


async def main() -> None:
    out = ROOT / "docs" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    video_dir = ROOT / ".cotal" / "gif" / "video"
    shutil.rmtree(video_dir, ignore_errors=True)
    video_dir.mkdir(parents=True)
    log = ROOT / ".cotal" / "gif" / "agent.log"
    log.unlink(missing_ok=True)

    agent = subprocess.Popen(
        ["uv", "run", "--group", "classifier", "python", str(ROOT / "scripts" / "flow_sim.py"), "--manual"],
        cwd=ROOT, env={**os.environ}, stdout=log.open("w"), stderr=subprocess.STDOUT,
    )
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(
                viewport={"width": W, "height": H}, device_scale_factor=1,
                record_video_dir=str(video_dir), record_video_size={"width": W, "height": H},
            )
            page = await context.new_page()
            s = Stage(page)
            await page.goto(f"{ORIGIN}/app/demo-stage.html")
            s.frame = page.frame(name="wallet") or next(f for f in page.frames if f.url.endswith("/app/"))
            await s.frame.wait_for_selector('[data-action="auth-mode"]')
            await asyncio.sleep(0.6)
            await page.evaluate("() => window.scene('title')")
            await asyncio.sleep(2.0)
            await page.evaluate("() => window.scene('stage')")
            await page.evaluate("() => window.scene('lead', 'Meet Alex.', 'Groceries every week. No time, and no wish to hand an AI the card.')")
            await asyncio.sleep(1.3)
            await s.click('[data-action="auth-mode"]', after=0.3)
            await s.type_into("#username", "alex", per_char=0.03)
            await s.type_into("#password", "demo-password-1", per_char=0.012)
            await s.click('[data-action="register"]', after=0.4)
            await s.frame.wait_for_selector("#shop-prompt")

            await page.evaluate("() => window.scene('lead', 'One sentence.', 'That is the whole setup. Limits, shops, what counts as groceries.')")
            await s.type_into("#shop-prompt", INSTRUCTION, per_char=0.006)
            await asyncio.sleep(0.4)
            await page.evaluate("() => window.scene('agent')")
            await s.say("user", INSTRUCTION, 0.5)
            await s.say("agent", "On it. First I need your Wallet's permission, so I am asking to connect.", 0.3)
            await s.tool("connect", 'agent_label="Grocery helper"', 0.3)

            await wait_for_agent(log, "connection request is waiting")
            await s.caption("The agent asks to connect. Nothing to type, no link to open.", 0.2)
            await s.click('nav [data-route="wallet"]', after=0.6)
            await s.frame.wait_for_selector('[data-action="approve-pending-pair"]')
            await asyncio.sleep(0.4)
            await s.click('[data-action="approve-pending-pair"]', after=0.4)
            await s.done()
            await s.say("agent", "Connected. Turning your sentence into a spending plan for you to confirm.", 0.3)
            await s.tool("propose_task_policy", "instruction, proposal{6 rules, 1 question}")
            await wait_for_agent(log, "policy proposed")
            await s.done(0.2)
            await s.tool("wait_for_policy", "draft_id")
            await s.caption("The plan waits in the Wallet. Only Alex can authorize it.", 0.2)
            await s.frame.wait_for_selector('[data-action="open-draft"]', timeout=15000)
            await asyncio.sleep(0.5)
            await s.click('[data-action="open-draft"]', after=0.7)
            await s.caption("Plain-English rules, in Alex's own words.", 0.5)
            await s.scroll(720, steps=12)
            await s.caption("One open question, answered where it is confirmed.", 0.3)
            await s.click('[data-action="answer-question"]', after=0.5)
            await s.click('[data-action="confirm"]', after=0.8)
            await wait_for_agent(log, "policy confirmed")
            await s.done()
            await s.caption("Permission active. The agent shops.", 0.3)
            await s.say("agent", "Confirmed. Ordering the weekly basket at Alpine Basket, CHF 35.00 with delivery.", 0.3)
            await s.tool("buy", "mandate_id, cart[1], merchant=Alpine Basket, total_chf=35.0, facts[1]")

            await wait_for_agent(log, "agent: buy ->")
            await s.done(0.2)
            await s.say("agent", "The Wallet wants your word on this one. It is asking you now.", 0.2)
            await s.tool("wait_for_purchase", "authorization_id")
            await s.click('[data-action="wallet-tab"][data-tab="needs"]', after=0.5)
            await s.frame.wait_for_selector('[data-action="open-pending"]', timeout=15000)
            await s.caption("The cart is judged by the Wallet: rules, card history, risk models.", 0.4)
            await s.click('[data-action="open-pending"]', after=1.0)
            await s.caption("A new device and a risk-model flag. Alex decides, the agent never does.", 1.1)
            await s.click('[data-action="resolve"][data-decision="approve"]', after=0.6)
            await wait_for_agent(log, "customer answered")
            await s.done()
            await s.say("agent", "Approved. Order placed. Trying a second shop for the missing items.", 0.3)
            await s.tool("buy", "mandate_id, merchant=Fresh Corner Market, total_chf=35.0")
            await wait_for_agent(log, "agent: done")
            await s.done(0.2)
            await s.say("agent", "Declined: you said shops you already use, and this card has never bought there. I will stay with Alpine Basket.", 0.6)

            await s.caption("Every decision is on record, with the reason.", 0.3)
            await s.click('nav [data-route="activity"]', after=0.8)
            await s.frame.wait_for_selector('[data-action="open-detail"]')
            await asyncio.sleep(0.3)
            await s.click('[data-action="open-detail"] >> nth=0', after=1.0)
            await s.caption("Blocked by Alex's own rule, against the card's real history.", 0.9)
            await s.click(".overlay-close", after=0.3)
            await s.click('[data-action="open-detail"] >> nth=1', after=0.6)
            await s.click('[data-action="inspector"][data-tab="summary"]', after=0.5)
            await s.caption("Under the hood: four stages, one decision.", 0.3)
            await s.click('[data-action="inspector"][data-tab="pipeline"]', after=0.7)
            await s.scroll(900, steps=22)
            await s.caption("Live risk models: a CatBoost history score and Jev's probabilities.", 1.0)
            await s.scroll(520, steps=16)
            await asyncio.sleep(0.8)
            await page.evaluate("() => window.hideCursor()")
            await page.evaluate("() => window.scene('outro', 'Agent on a Leash', 'Your agent buys. Your Wallet decides.')")
            await asyncio.sleep(2.4)
            await context.close()
            await browser.close()
    finally:
        if agent.poll() is None:
            agent.terminate()

    videos = list(video_dir.glob("*.webm"))
    if len(videos) != 1:
        raise RuntimeError(f"expected one recording, found {videos}")
    mp4 = out / "leash-user-flow.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(videos[0]),
                    "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                    "-movflags", "+faststart", str(mp4)], check=True)
    gif = out / "leash-user-flow.gif"
    palette = video_dir / "palette.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp4), "-vf",
                    "fps=10,scale=800:-1:flags=lanczos,palettegen=max_colors=128:stats_mode=diff", str(palette)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp4), "-i", str(palette), "-lavfi",
                    "fps=10,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                    str(gif)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                           capture_output=True, text=True, check=True).stdout.strip()
    print(f"mp4: {mp4} {mp4.stat().st_size // 1024} KB, {float(probe):.0f} s")
    print(f"gif: {gif} {gif.stat().st_size // 1024} KB")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
