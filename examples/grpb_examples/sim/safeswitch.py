"""SafeSwitch: a building controller commands actuators (valves, door locks) while some of them fail.

Actuators run in --groups separate processes (think: one power circuit or network segment each).
Every actuator is a server; the controller sends each one a command every --period seconds and gives
up after --deadline. At --fail-at, group 0 fails for --outage seconds:

  crash    the group's process is killed (power cut), then restarted
  freeze   the group's process is stopped (network partition: no packets, no clean disconnect), then resumed
  none     no failure (baseline latency)

Every command an actuator executes is logged to disk with the time it was issued and the time it
ran, so the run can count *stale* executions: commands carried out after the controller had already
given up on them (a door unlocking 10 s late). Three transports, same commands:

  grpb   gRPB-M2M: typed calls over MQTT, presence + Last Will, message expiry
  grpc   plain gRPC over HTTP/2 (the controller connects to each actuator directly)
  json   the usual MQTT way: QoS 1 commands to a persistent session, JSON acks on a reply topic

    python -m grpb_examples.sim safeswitch --transport grpb --scenario crash --actuators 20 --duration 40

Needs the broker for grpb and json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent import futures
from pathlib import Path
from typing import Any

import grpc
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

import grpb
from grpb.config import Config

from . import common
from . import safeswitch_pb2 as pb
from . import safeswitch_pb2_grpc as pb_grpc

TRANSPORTS = ("grpb", "grpc", "json")
SCENARIOS = ("crash", "freeze", "none")


def server_id(run_id: str, act: str) -> str:
    return f"ss-{run_id}-{act}"


def json_topics(run_id: str, act: str) -> tuple[str, str]:
    return f"naive/ss/{run_id}/cmd/{act}", f"naive/ss/{run_id}/ack/{act}"


# --- actuator group (its own process) ----------------------------------------------------------


class ExecLog:
    """Append-only record of executed commands; survives the process being killed."""

    def __init__(self, path: str) -> None:
        self._f = open(path, "a", buffering=1)
        self._lock = threading.Lock()

    def write(self, act: str, seq: int, issued_us: int, on: bool) -> int:
        applied = common.now_us()
        with self._lock:
            self._f.write(f"{act},{seq},{issued_us},{applied},{int(on)},{os.getpid()}\n")
        return applied


class ActuatorServicer(pb_grpc.ActuatorServicer):
    def __init__(self, act: str, log: ExecLog) -> None:
        self.act, self.log, self.on = act, log, False

    def Apply(self, request: pb.Command, context: grpc.ServicerContext) -> pb.State:
        self.on = request.on
        applied = self.log.write(self.act, request.seq, request.issued_us, request.on)
        return pb.State(actuator_id=self.act, seq=request.seq, on=self.on, applied_us=applied)


def group_main(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    log = ExecLog(args.log)
    ids = args.ids.split(",")
    ports = [int(p) for p in args.ports.split(",")] if args.ports else []
    servers: list[Any] = []
    clients: list[mqtt.Client] = []
    for i, act in enumerate(ids):
        if args.transport == "grpb":
            s = grpb.MqttServer(server_id(args.run_id, act), cfg.broker_host, cfg.broker_port,
                                max_workers=4, keepalive=args.keepalive)
        elif args.transport == "grpc":
            s = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
            s.add_insecure_port(f"127.0.0.1:{ports[i]}")
        else:
            clients.append(json_actuator(cfg, args.run_id, act, log, args.keepalive))
            continue
        pb_grpc.add_ActuatorServicer_to_server(ActuatorServicer(act, log), s)
        s.start()
        servers.append(s)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    for s in servers:
        s.stop(0)
    for c in clients:
        c.disconnect()
        c.loop_stop()


def json_actuator(cfg: Config, run_id: str, act: str, log: ExecLog, keepalive: int) -> mqtt.Client:
    """The common MQTT pattern: a persistent session so no command is lost while offline."""
    cmd_topic, ack_topic = json_topics(run_id, act)
    c = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=server_id(run_id, act), protocol=mqtt.MQTTv5)

    def on_message(client: mqtt.Client, userdata: Any, m: Any) -> None:
        d = json.loads(m.payload)
        applied = log.write(act, d["seq"], d["issued_us"], d["on"])
        client.publish(ack_topic, json.dumps({"seq": d["seq"], "applied_us": applied}), qos=1)

    props = Properties(PacketTypes.CONNECT)
    props.SessionExpiryInterval = 3600
    c.on_message = on_message
    c.on_connect = lambda client, u, f, rc, p: client.subscribe(cmd_topic, qos=1)
    c.connect(cfg.broker_host, cfg.broker_port, keepalive=keepalive, clean_start=False, properties=props)
    c.loop_start()
    return c


# --- controller ---------------------------------------------------------------------------------


class JsonController:
    """Publishes JSON commands and waits for the matching ack."""

    def __init__(self, cfg: Config, run_id: str) -> None:
        self.run_id = run_id
        self._acks: dict[tuple[str, int], threading.Event] = {}
        self._lock = threading.Lock()
        self._mq = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"ss-{run_id}-ctrl", protocol=mqtt.MQTTv5)
        self._mq.on_message = self._on_ack
        ready = threading.Event()
        self._mq.on_subscribe = lambda *a: ready.set()
        self._mq.on_connect = lambda c, u, f, rc, p: c.subscribe(f"naive/ss/{run_id}/ack/+", qos=1)
        self._mq.connect(cfg.broker_host, cfg.broker_port, keepalive=15)
        self._mq.loop_start()
        ready.wait(5)

    def _on_ack(self, c: Any, u: Any, m: Any) -> None:
        act = m.topic.rsplit("/", 1)[-1]
        seq = json.loads(m.payload)["seq"]
        with self._lock:
            ev = self._acks.get((act, seq))
        if ev:
            ev.set()

    def apply(self, act: str, cmd: pb.Command, deadline: float) -> str:
        ev = threading.Event()
        with self._lock:
            self._acks[(act, cmd.seq)] = ev
        try:
            payload = json.dumps({"actuator_id": act, "seq": cmd.seq, "issued_us": cmd.issued_us, "on": cmd.on})
            self._mq.publish(json_topics(self.run_id, act)[0], payload, qos=1)
            return "OK" if ev.wait(deadline) else "TIMEOUT"
        finally:
            with self._lock:
                self._acks.pop((act, cmd.seq), None)

    def close(self) -> None:
        self._mq.disconnect()
        self._mq.loop_stop()


def free_ports(n: int) -> list[int]:
    socks, ports = [], []
    for _ in range(n):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        socks.append(s)
        ports.append(s.getsockname()[1])
    for s in socks:
        s.close()
    return ports


class Group:
    def __init__(self, idx: int, ids: list[str], ports: list[int], args: argparse.Namespace, run_id: str,
                 log_dir: Path) -> None:
        self.idx, self.ids, self.ports = idx, ids, ports
        self.log = log_dir / f"group{idx}.csv"
        self.cmd = [sys.executable, "-m", "grpb_examples.sim", "safeswitch-group", "--transport", args.transport,
                    "--ids", ",".join(ids), "--run-id", run_id, "--log", str(self.log),
                    "--keepalive", str(args.keepalive), "--ports", ",".join(map(str, ports))]
        self.proc: subprocess.Popen | None = None
        self.frozen = False

    def start(self) -> None:
        self.proc = subprocess.Popen(self.cmd, env=os.environ.copy())

    def kill(self) -> None:
        if self.proc:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait(5)

    def freeze(self) -> None:
        if self.proc:
            self.proc.send_signal(signal.SIGSTOP)
            self.frozen = True

    def resume(self) -> None:
        if self.proc:
            self.proc.send_signal(signal.SIGCONT)
            self.frozen = False

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            if self.frozen:
                self.resume()
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def main(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    run = common.Run("safeswitch", args)
    run_id = uuid.uuid4().hex[:5]
    log_dir = Path(args.results_dir) / ".safeswitch" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    acts = [f"a{i:02d}" for i in range(args.actuators)]
    ports = free_ports(len(acts)) if args.transport == "grpc" else [0] * len(acts)
    per = -(-len(acts) // args.groups)
    groups = [Group(g, acts[g * per:(g + 1) * per], ports[g * per:(g + 1) * per], args, run_id, log_dir)
              for g in range(args.groups) if acts[g * per:(g + 1) * per]]
    group_of = {a: g.idx for g in groups for a in g.ids}
    affected = set(groups[0].ids) if args.scenario != "none" else set()
    run.log(f"safeswitch: {len(acts)} actuators in {len(groups)} groups, transport={args.transport}, "
            f"scenario={args.scenario} (group 0: {len(affected)} actuators), deadline={args.deadline}s, "
            f"keepalive={args.keepalive}s, netem={args.netem}")

    sampler = common.Sampler(common.find_pids())
    stop = threading.Event()
    channels: dict[str, Any] = {}
    jctl: JsonController | None = None
    marks: dict[str, int] = {}
    try:
        for g in groups:
            g.start()
        if args.transport == "json":
            jctl = JsonController(cfg, run_id)
        for a, port in zip(acts, ports):
            if args.transport == "grpb":
                channels[a] = grpb.MqttChannel(server_id(run_id, a), cfg.broker_host, cfg.broker_port,
                                               client_id=f"ss-{run_id}-c-{a}")
            elif args.transport == "grpc":
                channels[a] = grpc.insecure_channel(f"127.0.0.1:{port}",
                                                    options=[("grpc.use_local_subchannel_pool", 1)])
        stubs = {a: pb_grpc.ActuatorStub(ch) for a, ch in channels.items()}

        def apply(a: str, cmd: pb.Command) -> str:
            if jctl:
                return jctl.apply(a, cmd, args.deadline)
            try:
                stubs[a].Apply(cmd, timeout=args.deadline)
                return "OK"
            except grpc.RpcError as e:
                return e.code().name

        # Wait until every actuator answers once.
        t_ready = time.monotonic() + 20
        pending = set(acts)
        while pending and time.monotonic() < t_ready:
            for a in list(pending):
                if apply(a, pb.Command(actuator_id=a, seq=0, issued_us=common.now_us())) == "OK":
                    pending.discard(a)
            time.sleep(0.2)
        if pending:
            raise SystemExit(f"actuators not answering: {sorted(pending)} (is the broker running?)")

        phase = random.Random(args.seed)

        def control_loop(a: str, offset: float) -> None:
            seq, on = 0, False
            nxt = time.monotonic() + offset   # actuators out of step, like real control loops
            while common.sleep_until(nxt, stop):
                seq, on = seq + 1, not on
                issued = common.now_us()
                t0 = time.perf_counter()
                outcome = apply(a, pb.Command(actuator_id=a, seq=seq, issued_us=issued, on=on))
                elapsed = (time.perf_counter() - t0) * 1000
                run.add({"kind": "command", "t": round(run.t(), 3), "actuator": a, "group": group_of[a],
                         "affected": int(a in affected), "seq": seq, "issued_us": issued, "outcome": outcome,
                         "elapsed_ms": round(elapsed, 2)})
                nxt += args.period
                if nxt < time.monotonic():
                    nxt = time.monotonic()

        with common.Netem(args.netem):
            run.t0 = time.monotonic()
            run.t_measure = run.t0 + args.warmup
            sampler.start()
            threads = [threading.Thread(target=control_loop, args=(a, phase.uniform(0, args.period)), daemon=True)
                       for a in acts]
            for th in threads:
                th.start()
            run.event("start", transport=args.transport, scenario=args.scenario)
            common.sleep_until(run.t_measure, stop)
            marks["w0"] = common.now_us()
            run.event("measuring")
            if args.scenario != "none":
                common.sleep_until(run.t_measure + args.fail_at, stop)
                g0 = groups[0]
                marks["fail"] = common.now_us()
                if args.scenario == "crash":
                    g0.kill()
                else:
                    g0.freeze()
                run.event(f"{args.scenario}", group=0, actuators=len(g0.ids))
                common.sleep_until(run.t_measure + args.fail_at + args.outage, stop)
                marks["restore"] = common.now_us()
                if args.scenario == "crash":
                    g0.start()
                else:
                    g0.resume()
                run.event("restored", group=0)
            common.sleep_until(run.t_measure + args.duration, stop)
            marks["w1"] = common.now_us()
            stop.set()
            for th in threads:
                th.join(args.deadline + 2)
            run.event("stopped")
            time.sleep(1.0)
    finally:
        stop.set()
        sampler.stop()
        for g in groups:
            g.stop()
        for ch in channels.values():
            ch.close()
        if jctl:
            jctl.close()

    executions = read_logs(groups)
    shutil.rmtree(log_dir, ignore_errors=True)   # the executions are kept in samples.csv
    summary = summarize(run, args, marks, executions, affected, sampler)
    for e in executions:   # keep the raw execution log with the run
        run.add({"kind": "execution", **e})
    run.finish(summary, COLUMNS, resources=sampler.rows, notes=NOTES)


def read_logs(groups: list[Group]) -> list[dict]:
    rows = []
    for g in groups:
        if not g.log.exists():
            continue
        with g.log.open() as f:
            for r in csv.reader(f):
                if len(r) == 6 and r[1] != "0":
                    rows.append({"actuator": r[0], "seq": int(r[1]), "issued_us": int(r[2]), "applied_us": int(r[3]),
                                 "on": int(r[4]), "pid": int(r[5])})
    return rows


def summarize(run: common.Run, args: argparse.Namespace, marks: dict, executions: list[dict], affected: set,
              sampler: common.Sampler) -> dict:
    w0, w1 = marks["w0"], marks["w1"]
    cmds = [s for s in run.samples if s["kind"] == "command" and w0 <= s["issued_us"] < w1]
    deadline_us = args.deadline * 1e6
    normal = [s for s in cmds if not s["affected"] and s["outcome"] == "OK"]
    out: dict[str, Any] = {
        "app": "safeswitch", "transport": args.transport, "scenario": args.scenario, "actuators": args.actuators,
        "affected": len(affected), "netem": args.netem, "deadline_s": args.deadline, "keepalive_s": args.keepalive,
        "outage_s": args.outage if args.scenario != "none" else 0, "period_s": args.period, "commands": len(cmds),
        "ok_ratio": round(sum(s["outcome"] == "OK" for s in cmds) / len(cmds), 4) if cmds else "",
        "latency_p50_ms": common.pct([s["elapsed_ms"] for s in normal], 50),
        "latency_p95_ms": common.pct([s["elapsed_ms"] for s in normal], 95),
    }
    # Behaviour of the affected actuators while their group was down.
    if "fail" in marks:
        fail, restore = marks["fail"], marks["restore"]
        hit = [s for s in cmds if s["affected"] and fail <= s["issued_us"] < restore]
        failed = [s for s in hit if s["outcome"] != "OK"]
        fast = [s for s in failed if s["elapsed_ms"] < 0.25 * args.deadline * 1000]
        by_act: dict[str, list[dict]] = defaultdict(list)
        for s in cmds:
            if s["affected"]:
                by_act[s["actuator"]].append(s)
        first_err, fast_from, recovery = [], [], []
        for rows in by_act.values():
            done = [(s["issued_us"] + s["elapsed_ms"] * 1000, s) for s in rows]
            errs = [t for t, s in done if s["issued_us"] >= fail and s["outcome"] != "OK"]
            fasts = [t for t, s in done if s["issued_us"] >= fail and s["outcome"] != "OK"
                     and s["elapsed_ms"] < 0.25 * args.deadline * 1000]
            oks = [t for t, s in done if s["issued_us"] >= restore and s["outcome"] == "OK"]
            if errs:
                first_err.append((min(errs) - fail) / 1000)
            if fasts:
                fast_from.append((min(fasts) - fail) / 1000)
            if oks:
                recovery.append((min(oks) - restore) / 1000)
        out.update({
            "outage_commands": len(hit), "outage_failed": len(failed), "outage_fast_fail": len(fast),
            "outage_timed_out": sum(s["outcome"] in ("DEADLINE_EXCEEDED", "TIMEOUT") for s in failed),
            "controller_blocked_s": round(sum(s["elapsed_ms"] for s in failed) / 1000, 1),
            "first_error_ms": common.pct(first_err, 50),
            "fails_fast_after_ms": common.pct(fast_from, 50) if fast_from else "never",
            "recovery_ms": common.pct(recovery, 50),
        })
    # What actually ran on the actuators, compared with what the controller believed.
    outcome = {(s["actuator"], s["seq"]): s["outcome"] for s in run.samples if s["kind"] == "command"}
    seen: dict[tuple[str, int], int] = defaultdict(int)
    stale, unacked, late_ms = 0, 0, []
    for e in executions:
        if not w0 <= e["issued_us"] < w1:
            continue
        key = (e["actuator"], e["seq"])
        seen[key] += 1
        lateness = e["applied_us"] - e["issued_us"]
        if lateness > deadline_us:
            stale += 1
            late_ms.append(lateness / 1000)
        if outcome.get(key, "OK") != "OK":
            unacked += 1
    out.update({
        "executions": len(executions), "stale_executions": stale,
        "stale_max_late_s": round(max(late_ms) / 1000, 2) if late_ms else 0,
        "executed_but_reported_failed": unacked,
        "duplicate_executions": sum(n - 1 for n in seen.values() if n > 1),
        **sampler.means(),
    })
    return out


COLUMNS = [("transport", "transport"), ("scenario", "scenario"), ("netem", "network"),
           ("latency_p50_ms", "p50 ms"), ("outage_commands", "cmds in outage"), ("outage_fast_fail", "fast fail"),
           ("outage_timed_out", "timed out"), ("controller_blocked_s", "ctrl blocked s"),
           ("fails_fast_after_ms", "fails fast after ms"), ("recovery_ms", "recovery ms"),
           ("stale_executions", "STALE executions"), ("stale_max_late_s", "max late s"),
           ("executed_but_reported_failed", "ran but reported failed")]

NOTES = ("STALE = a command executed more than the deadline after it was issued, i.e. after the controller had "
         "given up on it. ran but reported failed = the controller recorded an error, yet the actuator carried "
         "the command out. fails fast after = time from the failure until commands to the dead group fail "
         "immediately instead of waiting for the deadline (median over the group's actuators).")


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("safeswitch", help="command and control while actuators crash or freeze",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--transport", choices=TRANSPORTS, default="grpb")
    p.add_argument("--scenario", choices=SCENARIOS, default="crash")
    p.add_argument("--actuators", type=int, default=20)
    p.add_argument("--groups", type=int, default=4, help="actuator processes; group 0 is the one that fails")
    p.add_argument("--period", type=float, default=0.5, help="seconds between commands per actuator")
    p.add_argument("--deadline", type=float, default=2.0, help="controller timeout per command (seconds)")
    p.add_argument("--fail-at", type=float, default=10.0, help="seconds into the measured window")
    p.add_argument("--outage", type=float, default=10.0, help="seconds the group stays down")
    p.add_argument("--keepalive", type=int, default=5, help="MQTT keepalive of the actuators (seconds)")
    p.add_argument("--seed", type=int, default=1, help="random seed for the control loops' phases")
    common.add_args(p, duration=40, warmup=3)
    p.set_defaults(func=main)

    g = sub.add_parser("safeswitch-group", help=argparse.SUPPRESS)
    g.add_argument("--transport", choices=TRANSPORTS, required=True)
    g.add_argument("--ids", required=True)
    g.add_argument("--run-id", required=True)
    g.add_argument("--log", required=True)
    g.add_argument("--keepalive", type=int, default=5)
    g.add_argument("--ports", default="")
    g.set_defaults(func=group_main)
