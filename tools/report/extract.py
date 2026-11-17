"""Pull the report's numbers out of an evidence folder into data.json (every number traceable to a CSV)."""
import csv
import glob
import json
import struct
import sys
from pathlib import Path

ev = Path(sys.argv[1])
out = Path(sys.argv[2])


def rows(app):
    f = glob.glob(str(ev / f"*sweep-{app}-*" / "combined.csv"))[0]
    return [r for r in csv.DictReader(open(f)) if not r.get("error")]


def png_size(p):
    with open(p, "rb") as fh:
        head = fh.read(24)
    return struct.unpack(">II", head[16:24])


env = json.load(open(glob.glob(str(ev / "*sweep-farmnet-*" / "runs" / "*" / "env.json"))[0]))
codec_runs = sorted(glob.glob("results/*-codec-*/summary.csv"))   # optional: make bench ARGS="codec ..."
codec = list(csv.DictReader(open(codec_runs[-1]))) if codec_runs else []
data = {
    "evidence_dir": str(ev), "machine": env["platform"], "device_model": env.get("device_model", ""),
    "host": env.get("host", ""), "date": env.get("time", "")[:10], "cpus": env["cpu_count"], "python": env["python"],
    "farmnet": rows("farmnet"), "pulse": rows("pulse"), "safeswitch": rows("safeswitch"), "codec": codec,
    "charts": {Path(p).stem: {"path": str(Path(p).resolve()), "size": png_size(p)}
               for p in glob.glob(str(ev / "charts" / "*.png"))},
}
out.write_text(json.dumps(data, indent=1))
print(f"wrote {out}: {len(data['farmnet'])} farmnet, {len(data['pulse'])} pulse, "
      f"{len(data['safeswitch'])} safeswitch rows, {len(data['charts'])} charts")
