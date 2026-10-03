#!/usr/bin/env python3
"""Render the Rolex history video (1920x1080, 24 fps) from stills, clips and narration.

Inputs (cwd): assets.tsv lines "kind<TAB>index<TAB>url-suffix" (kind: img|aud|vid),
shots.json [[segment, shot_index, callout], ...]. Output: out/final.mp4
"""
import json, os, subprocess, sys

BASE = "https://d8j0ntlcm91z4.cloudfront.net/user_3JzmjTsdGKQPbIPQq5Hs3dLxR7C/hf_20261003_"
FPS = 24
W, H = 1920, 1080
GAP = 0.45          # pause between narration segments
LEAD = 0.4          # silence before the first line
TAIL = 2.0          # hold after the last line
CLIP_LEN = 4.0
FONT = "/usr/share/fonts/truetype/higgsfield/Montserrat-ExtraBold.ttf"


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"failed: {cmd[:200]}")
    return r.stdout


def dur(path):
    return float(sh(f"ffprobe -v error -show_entries format=duration -of csv=p=0 '{path}'").strip())


os.makedirs("dl", exist_ok=True)
os.makedirs("shots", exist_ok=True)
os.makedirs("out", exist_ok=True)

shots = json.load(open("shots.json"))
if os.environ.get("SEGS"):
    keep = {int(v) for v in os.environ["SEGS"].split(",")}
    shots = [x for x in shots if x[0] in keep]
segments = sorted({s[0] for s in shots})
need = {("img", x[1]) for x in shots} | {("vid", x[1]) for x in shots} | {("aud", s) for s in segments}

assets = {}
for line in open("assets.tsv"):
    kind, idx, suffix = line.split()
    if (kind, int(idx)) not in need:
        continue
    ext = suffix.rsplit(".", 1)[1]
    path = f"dl/{kind}{int(idx):02d}.{ext}"
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        sh(f"curl -fsSL --retry 3 --retry-all-errors '{BASE}{suffix}' -o '{path}'")
    assets[(kind, int(idx))] = path
print("downloaded", len(assets), flush=True)

# Narration track: lead + seg1 + gap + seg2 ... + tail. Each segment's visual window
# spans its line plus the following gap, so cuts land in the pauses.
seg_len = {}
parts = []
sh(f"ffmpeg -v error -y -f lavfi -i anullsrc=r=48000:cl=stereo -t {GAP} dl/gap.wav")
sh(f"ffmpeg -v error -y -f lavfi -i anullsrc=r=48000:cl=stereo -t {LEAD} dl/lead.wav")
sh(f"ffmpeg -v error -y -f lavfi -i anullsrc=r=48000:cl=stereo -t {TAIL} dl/tail.wav")
for s in segments:
    src = assets[("aud", s)]
    norm = f"dl/n{s:02d}.wav"
    sh(f"ffmpeg -v error -y -i '{src}' -ar 48000 -ac 2 '{norm}'")
    d = dur(norm)
    seg_len[s] = d + (GAP if s != segments[-1] else TAIL)
    if s == segments[0]:
        seg_len[s] += LEAD
        parts.append("dl/lead.wav")
    parts.append(norm)
    parts.append("dl/gap.wav" if s != segments[-1] else "dl/tail.wav")
with open("dl/alist.txt", "w") as f:
    f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
sh("ffmpeg -v error -y -f concat -safe 0 -i dl/alist.txt -c:a pcm_s16le dl/narration.wav")
total_audio = dur("dl/narration.wav")
print("narration", round(total_audio, 2), {k: round(v, 2) for k, v in seg_len.items()}, flush=True)

# Allocate frame counts per shot. Animated shots get CLIP_LEN; stills share the rest.
plan = []
frame_cursor = 0
time_cursor = 0.0
for s in segments:
    seg_shots = [x for x in shots if x[0] == s]
    end_frame = round((time_cursor + seg_len[s]) * FPS)
    budget = end_frame - frame_cursor
    clips = [x for x in seg_shots if ("vid", x[1]) in assets]
    stills = [x for x in seg_shots if ("vid", x[1]) not in assets]
    clip_frames = round(CLIP_LEN * FPS)
    still_budget = budget - clip_frames * len(clips)
    per = still_budget // max(1, len(stills))
    extra = still_budget - per * len(stills)
    for x in seg_shots:
        if ("vid", x[1]) in assets:
            n = clip_frames
        else:
            n = per + (1 if extra > 0 else 0)
            extra -= 1
        plan.append((x[1], n, x[2]))
    frame_cursor = end_frame
    time_cursor += seg_len[s]

MOVES = [
    ("1+0.14*on/{N}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),             # push in
    ("1.14-0.14*on/{N}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),          # pull out
    ("1.12", "(iw-iw/zoom)*on/{N}", "ih/2-(ih/zoom/2)"),                   # pan right
    ("1.12", "(iw-iw/zoom)*(1-on/{N})", "ih/2-(ih/zoom/2)"),               # pan left
    ("1+0.10*on/{N}", "(iw-iw/zoom)*0.3", "(ih-ih/zoom)*0.3"),             # drift in, top-left
]


def callout_filter(text):
    if not text:
        return ""
    t = text.replace(":", r"\:").replace("'", "")
    return (f",drawtext=fontfile={FONT}:text='{t}':fontsize=104:fontcolor=white"
            f":borderw=7:bordercolor=black@0.85:shadowx=6:shadowy=6:shadowcolor=black@0.5"
            f":x=90:y=80:alpha='if(lt(t,0.35),0,min(1,(t-0.35)/0.25))'")


TIGHT = [
    ("1.30+0.08*on/{N}", "(iw-iw/zoom)*0.15", "(ih-ih/zoom)*0.25"),
    ("1.38-0.08*on/{N}", "(iw-iw/zoom)*0.85", "(ih-ih/zoom)*0.35"),
    ("1.32", "(iw-iw/zoom)*(0.2+0.6*on/{N})", "(ih-ih/zoom)*0.5"),
    ("1.28+0.10*on/{N}", "(iw-iw/zoom)*0.5", "(ih-ih/zoom)*0.6"),
]
MAX_SUB = 5 * FPS  # longest single framing before we cut to a new one

renders = []  # (image/clip index, frames, callout, kind, move)
k = 0
for idx, n, text in plan:
    if ("vid", idx) in assets:
        renders.append((idx, n, text, "vid", None))
        continue
    parts = max(1, -(-n // MAX_SUB))
    base = n // parts
    for p in range(parts):
        fn = base + (n - base * parts if p == parts - 1 else 0)
        move = MOVES[k % len(MOVES)] if p == 0 else TIGHT[(k + p) % len(TIGHT)]
        renders.append((idx, fn, text if p == 0 else "", "img", move))
    k += 1

for i, (idx, n, text, kind, move) in enumerate(renders):
    out = f"shots/{i:03d}.mp4"
    if os.path.exists(out) and os.path.getsize(out) > 0:
        continue
    if kind == "vid":
        vf = (f"scale={W}:{H}:flags=lanczos,fps={FPS},setsar=1" + callout_filter(text) +
              f",tpad=stop_mode=clone:stop_duration=2,format=yuv420p")
        sh(f"ffmpeg -v error -y -i '{assets[('vid', idx)]}' -vf \"{vf}\" -frames:v {n} -an "
           f"-c:v libx264 -preset veryfast -crf 18 -r {FPS} '{out}'")
    else:
        z, x, y = (m.format(N=n) for m in move)
        vf = (f"scale=3840:2160:flags=lanczos,zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},"
              f"setsar=1" + callout_filter(text) + ",format=yuv420p")
        sh(f"ffmpeg -v error -y -loop 1 -framerate {FPS} -i '{assets[('img', idx)]}' -vf \"{vf}\" "
           f"-frames:v {n} -c:v libx264 -preset veryfast -crf 18 -r {FPS} '{out}'")
    print("shot", i, idx, n, flush=True)

with open("shots/list.txt", "w") as f:
    f.writelines(f"file '{os.path.abspath(f'shots/{i:03d}.mp4')}'\n" for i in range(len(renders)))
sh("ffmpeg -v error -y -f concat -safe 0 -i shots/list.txt -c copy out/video.mp4")
vlen = dur("out/video.mp4")
fade_out = max(0.0, vlen - 1.2)
sh(f"ffmpeg -v error -y -i out/video.mp4 -i dl/narration.wav "
   f"-vf \"fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out:.2f}:d=1.2\" "
   f"-af \"loudnorm=I=-15:TP=-1.5:LRA=11,afade=t=out:st={fade_out:.2f}:d=1.2\" "
   f"-c:v libx264 -preset medium -crf 18 -profile:v high -pix_fmt yuv420p -r {FPS} "
   f"-c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart out/final.mp4")
print("FINAL", sh("ffprobe -v error -show_entries format=duration,size:stream=width,height,r_frame_rate,codec_name "
                  "-of compact out/final.mp4"), flush=True)
