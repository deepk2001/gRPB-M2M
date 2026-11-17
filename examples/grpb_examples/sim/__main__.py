"""gRPB-M2M simulations: many nodes on one machine, with data points for every claim.

    python -m grpb_examples.sim farmnet    --nodes 50 --format pb        sensor fleet through oneM2M
    python -m grpb_examples.sim pulse      --transport grpb --hz 20      high-rate streaming to viewers
    python -m grpb_examples.sim safeswitch --transport grpb --scenario crash   commands while actuators fail
    python -m grpb_examples.sim dashboard                                FarmNet data over HTTP/JSON
    python -m grpb_examples.sim sweep farmnet --vary format=json,cbor,pb -- --duration 30
    python -m grpb_examples.sim plot results/<sweep>
    python -m grpb_examples.sim netem 4g | clear                         network profile on loopback (Linux)

Every run takes --duration, --warmup, --netem, --label and --no-save; see each command's --help.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import common, dashboard, farmnet, plot, pulse, safeswitch, sweep


def netem_main(args: argparse.Namespace) -> None:
    n = common.Netem("lan")
    if args.profile == "clear":
        n.clear()
        print("loopback network emulation cleared")
    else:
        n = common.Netem(args.profile)
        n.set(n.spec)
        print(f"loopback now: {n.spec}  (clear with: python -m grpb_examples.sim netem clear)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m grpb_examples.sim", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(required=True, metavar="command")
    farmnet.add_parser(sub)
    pulse.add_parser(sub)
    safeswitch.add_parser(sub)
    dashboard.add_parser(sub)
    sweep.add_parser(sub)
    plot.add_parser(sub)
    n = sub.add_parser("netem", help="apply a network profile to loopback by hand (Linux)")
    n.add_argument("profile", help=f"{', '.join(common.NETEM_PROFILES)}, a raw netem spec, or clear")
    n.set_defaults(func=netem_main)
    argv = sys.argv[1:]
    fixed: list[str] = []
    if argv[:1] == ["sweep"] and "--" in argv:   # sweep ... -- <options for every run>
        i = argv.index("--")
        argv, fixed = argv[:i], argv[i + 1:]
    args = ap.parse_args(argv)
    if argv[:1] == ["sweep"]:
        args.fixed = fixed
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
