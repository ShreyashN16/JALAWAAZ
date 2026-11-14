"""Compose 1920x1080 frames from raw screenshots + storyboard, then encode the video.

    python compose.py frames full|short       # write frames/<cut>/NN_<id>.jpg
    python compose.py render full|short       # encode scenes and join into out/<file>.mp4
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "raw"
D = lambda t: f'<span class="deva" lang="mr">{t}</span>'   # Devanagari span

FULL = [
    dict(card="title", d=6.0),
    dict(id="p01_home", d=5.5, n="1", act="Missed call", cap="A villager gives a missed call. It costs nothing.",
         sub="The phone is in Marathi here; Hindi and Hinglish work the same way."),
    dict(id="p02_wait", d=4.5, n="1", act="Missed call", cap="Jal Awaaz calls back.",
         sub="In this demo the callback is simulated in the browser, a few seconds later."),
    dict(id="p03_ring", d=4.0, n="1", act="Missed call", cap="The callback rings.", sub=""),
    dict(id="p04_greet", d=7.0, n="2", act="Report", cap="The first sentence says it is an AI assistant.",
         sub="Then it asks where and what the problem is, one question at a time."),
    dict(id="p05_said", d=8.5, n="2", act="Report", cap="The caller describes the fault in one sentence.",
         sub=f"{D('“खेड शिवापूरमध्ये हातपंप 3 दिवस बंद आहे, 40 घरं”')}, typed here. "
             "On the right: what was understood."),
    dict(id="p06_readback", d=7.0, n="2", act="Report", cap="Before any ticket, everything is read back.",
         sub=f"A fixed template, not model-written text. The caller answers {D('हो')} or {D('नाही')}."),
    dict(id="p07_ticket", d=6.0, n="2", act="Report", cap=f"Only after {D('“हो”')} is a ticket created.",
         sub="The number is spoken digit by digit and sent by SMS (logged in this demo)."),
    dict(id="d01_newpin", d=7.0, n="3", act="District dashboard", cap="A red pin appears for Khed Shivapur.",
         sub="Red means open. The queue shows each ticket's priority and the reason for it."),
    dict(id="d02_drawer", d=6.5, n="3", act="District dashboard", cap="Every priority comes with its reason.",
         sub="Rules in code set priority and SLA. The model only extracts the fields."),
    dict(id="e01_queue", d=6.0, n="4", act="Engineer", cap="The engineer's queue, most urgent first.",
         sub="Each job shows why it has its priority and when its SLA runs out."),
    dict(id="e02_acked", d=4.0, n="4", act="Engineer", cap="One tap to acknowledge.", sub=""),
    dict(id="e03_sheet", d=7.0, n="4", act="Engineer", cap="Reporting a fix does not close the ticket.",
         sub="The sheet says so: Jal Awaaz will call the person who reported it."),
    dict(id="d03_amber", d=5.5, n="4", act="Engineer", cap="The pin turns amber: fix claimed, not confirmed.", sub=""),
    dict(id="p08_vring", d=5.0, n="5", act="Verification", cap="The original caller gets a second call.",
         sub="Time is compressed: in real use this call comes hours after the fix."),
    dict(id="p09_vask", d=6.5, n="5", act="Verification", cap="It asks one concrete question: is the hand pump working now?",
         sub="It names the ticket and the village, and says again that it is an AI."),
    dict(id="p10_verified", d=5.0, n="5", act="Verification", cap=f"{D('“हो”')}: the caller closes the ticket.", sub=""),
    dict(id="d04_green", d=6.0, n="5", act="Verification", cap="The pin turns green.",
         sub="Verified by the person who reported it, not by the engineer."),
    dict(id="p11_ticket2", d=6.0, n="6", act="The reopen", cap="A second complaint: no tap water in Donje for 2 days.",
         sub="Reported the same way. The engineer then reports a fix."),
    dict(id="p12_vask2", d=5.0, n="6", act="The reopen", cap="The verification call asks again.", sub=""),
    dict(id="p13_reopened", d=6.0, n="6", act="The reopen", cap=f"{D('“नाही”')}: the ticket reopens.",
         sub="Its priority goes up one level, and it counts as a false closure."),
    dict(id="d05_rate", d=7.0, n="6", act="The reopen", cap="The headline number moves: false-closure rate 50%, n = 2.",
         sub="Tickets reopened at least once ÷ tickets whose fix the caller answered."),
    dict(id="d06_drawer2", d=6.0, n="6", act="The reopen", cap="The reason records it: P2 became P1.",
         sub="“60 households (>= 50); reopened 1x after a false closure (P2 -> P1)”"),
    dict(id="d07_full", d=7.0, n="", act="Dashboard", cap="With 14 synthetic tickets added, each labelled synthetic.",
         sub="Repeat failures, SLA breaches, a 14-day trend and the audit trail of every ticket."),
    dict(id="m01_metrics", d=7.5, n="", act="Evaluation", cap="Only measured numbers, each with its n.",
         sub="Held-out text test: village, source and fault all right in 12 of 15. Speech on real audio: not measured yet."),
    dict(card="close", d=9.0),
]

SHORT = [
    dict(card="title", d=4.0),
    dict(id="p01_home", d=3.5, n="1", act="Missed call", cap="A villager gives a missed call.", sub=""),
    dict(id="p04_greet", d=4.0, n="2", act="Report", cap="The callback says it is an AI.", sub=""),
    dict(id="p05_said", d=4.5, n="2", act="Report", cap="The caller describes the fault.", sub="Typed here; with a Gnani key, Prisma hears it."),
    dict(id="p06_readback", d=4.0, n="2", act="Report", cap="Everything is read back first.", sub=""),
    dict(id="p07_ticket", d=3.5, n="2", act="Report", cap=f"Ticket only after {D('“हो”')}.", sub=""),
    dict(id="d01_newpin", d=4.0, n="3", act="Dashboard", cap="A red pin on the district map.", sub=""),
    dict(id="e03_sheet", d=5.0, n="4", act="Engineer", cap="The engineer reports a fix.", sub="That does not close the ticket."),
    dict(id="p08_vring", d=3.5, n="5", act="Verification", cap="The caller gets a second call.", sub=""),
    dict(id="p10_verified", d=3.5, n="5", act="Verification", cap=f"{D('“हो”')}: verified by the caller.", sub=""),
    dict(id="d04_green", d=3.0, n="5", act="Verification", cap="The pin turns green.", sub=""),
    dict(id="p13_reopened", d=4.0, n="6", act="The reopen", cap=f"{D('“नाही”')}: reopened, priority up.", sub=""),
    dict(id="d05_rate", d=4.5, n="6", act="The reopen", cap="False-closure rate, always with its n.", sub=""),
    dict(card="close", d=5.5),
]
CUTS = {"full": (FULL, "jalawaaz_demo_2min.mp4"), "short": (SHORT, "jalawaaz_demo_60s.mp4")}
XF = 0.35   # crossfade seconds, inside each scene file
ENC = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60"]


def frames(cut):
    from playwright.sync_api import sync_playwright
    board, _ = CUTS[cut]
    moments = json.load(open(RAW / "moments.json"))["moments"]
    out = HERE / "frames" / cut
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("JA_CHROME"), args=["--no-sandbox", "--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        pg.goto((HERE / "compose.html").as_uri())
        for i, beat in enumerate(board):
            spec = dict(beat)
            if "id" in beat:
                m = moments[beat["id"]]
                spec.update(img=(RAW / m["img"]).as_uri(), boxes=m["boxes"])
            pg.evaluate("b => window.renderBeat(b)", spec)
            name = f"{i:02d}_{beat.get('id') or beat['card']}.jpg"
            pg.screenshot(path=str(out / name), type="jpeg", quality=92)
        b.close()
    print(f"{len(board)} frames in {out}")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:])
        raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:6])}...")


def render(cut):
    board, outname = CUTS[cut]
    fdir = HERE / "frames" / cut
    files = sorted(fdir.glob("*.jpg"))
    assert len(files) == len(board), (len(files), len(board))
    sdir = HERE / "scenes" / cut
    sdir.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, beat in enumerate(board):
        d = beat["d"]
        last = i == len(board) - 1
        a = f"[0:v]format=yuv420p,loop=-1:1,trim=duration={d},setpts=PTS-STARTPTS,fps=30,settb=AVTB"
        if i == 0:
            a += ",fade=t=in:st=0:d=0.5"
        if last:
            a += f",fade=t=out:st={d - 0.8:.2f}:d=0.8"
        cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", str(files[i])]
        if last:
            fc = a + "[v]"
        else:
            cmd += ["-framerate", "30", "-i", str(files[i + 1])]
            fc = (a + "[a];[1:v]format=yuv420p,loop=-1:1,trim=duration=" + str(XF) +
                  ",setpts=PTS-STARTPTS,fps=30,settb=AVTB[b];"
                  f"[a][b]xfade=transition=fade:duration={XF}:offset={d - XF:.3f},format=yuv420p[v]")
        tmp, final = sdir / f"{i:02d}.tmp.mp4", sdir / f"{i:02d}.mp4"
        run(cmd + ["-filter_complex", fc, "-map", "[v]", *ENC, str(tmp)])
        os.replace(tmp, final)
        parts.append(final)
    lst = sdir / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = sdir / "joined.tmp.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    outdir = HERE / "out"
    outdir.mkdir(exist_ok=True)
    tmp, final = outdir / ("tmp_" + outname), outdir / outname
    run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "64k", "-shortest",
         "-movflags", "+faststart", str(tmp)])
    os.replace(tmp, final)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final)],
                         capture_output=True, text=True).stdout.strip()
    print(f"{final}  {float(dur):.1f} s  {final.stat().st_size // 1024} KB  (storyboard {sum(b['d'] for b in board):.1f} s)")


if __name__ == "__main__":
    {"frames": frames, "render": render}[sys.argv[1]](sys.argv[2])
