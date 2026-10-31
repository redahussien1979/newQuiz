"""Render from the command line:
    python render_cli.py projects/example_timeline.json
    python render_cli.py projects/example_timeline.json outputs/my_video.mp4
    python render_cli.py projects/example_timeline.json --still 12.5      (saves one preview frame)
"""
import json
import os
import sys

from engine.render import render_still, render_video

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        project = json.load(f)
    base = os.path.splitext(os.path.basename(sys.argv[1]))[0]
    os.makedirs("outputs", exist_ok=True)
    if "--still" in sys.argv:
        t = float(sys.argv[sys.argv.index("--still") + 1])
        img, _ = render_still(project, t)
        out = f"outputs/{base}_{t:05.1f}s.png"
        img.save(out)
    else:
        out = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else f"outputs/{base}.mp4"
        render_video(project, out, progress=lambda p: print(f"\r{p * 100:5.1f}%", end="", flush=True))
        print()
    print("Saved:", out)
