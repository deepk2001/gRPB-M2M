# Simulations: evidence for gRPB-M2M

Three mock applications run many simulated nodes on one machine (a Raspberry Pi, or a laptop) and
record data points for each claim we make about gRPB-M2M. Every run saves its raw data, so any
number in the report or slides can be traced back to a CSV file.

| Claim | Simulation | Data points |
|---|---|---|
| Protobuf cuts the bytes a device sends and receives, at any fleet size | FarmNet | bytes per reading on the device link, fleet MB/day, by format |
| It stays standard oneM2M: existing JSON clients still read the data | FarmNet | containers read back over HTTP/JSON that match what the device wrote |
| Less data means lower delay and CSE load on constrained links | FarmNet | RTT p50/p95/p99 and CSE CPU per format, fleet size and network profile |
| Typed server streaming over MQTT keeps up at high rates, to several viewers | PulseWatch | samples/s achieved vs offered, delivery ratio, sensor-to-viewer delay |
| Dead devices are detected quickly and calls fail fast instead of hanging | SafeSwitch | time until calls fail fast, controller time spent blocked |
| Commands are never carried out late, after the controller gave up | SafeSwitch | stale executions, "ran but reported failed" |
| Devices recover quickly when they come back | SafeSwitch | time from restore to the first successful command |

## Setup

On the Pi (or laptop), from the repository:

```sh
make setup-pi                       # or make setup on a laptop
make broker                         # terminal 1
make cse ARGS="--headless --log-level warn"   # terminal 2: quiet logs, so logging doesn't skew timings
make evidence                       # terminal 3: everything, then charts (about 2 hours on a Pi 4)
QUICK=1 make evidence               # dry run: short runs, LAN only (about 10 minutes)
```

`make evidence` runs `scripts/run-evidence.sh`, which sweeps the three apps over formats, transports,
fleet sizes, rates and network profiles. It writes `results/<time>-evidence-<label>/` with one sweep
folder per app and `charts/` with the PNGs. Run settings: `DUR=30` (seconds per run), `NETS=lan,4g`
(network profiles), `LABEL=pi4` (name in folder names).

Network emulation (`--netem`) uses `tc netem` and needs Linux with passwordless sudo, which is the
Raspberry Pi OS default. On macOS only `lan` is available.

## The applications

### FarmNet: a sensor fleet through oneM2M

N farm sensors, each a oneM2M AE with its own MQTT connection, write a reading (soil moisture,
temperature, humidity, battery) to their container every few seconds through the patched ACME. An
"alert service" AE subscribes to every container and receives each reading as a notification. At the
end, ten containers are read back over HTTP as JSON and compared with what the devices wrote.

```sh
python -m grpb_examples.sim farmnet --nodes 50 --interval 5 --format pb --duration 60
python -m grpb_examples.sim farmnet --nodes 20 --interval 2 --duration 0 --keep   # live demo, Ctrl-C to stop
python -m grpb_examples.sim dashboard                       # http://<pi>:8090, reads the CSE over HTTP/JSON
```

| Summary column | Meaning |
|---|---|
| `device_link_B_per_reading` | Exact MQTT PUBLISH bytes for request + response on the device's own connection (topics and properties included, PUBACKs excluded) |
| `notify_B` | Bytes per notification delivered to the alert service |
| `fleet_MB_per_day` | `device_link_B_per_reading` × readings per day × nodes |
| `rtt_p50/p95/p99_ms` | Request sent until response received |
| `notify_p50/p95_ms` | Reading sent until the alert service received the notification |
| `interop_ok` / `interop_checked` | Containers whose latest value, read over HTTP as JSON, equals what the device wrote |
| `cse_cpu_mean`, `broker_cpu_mean`, `sim_cpu_mean` | Mean CPU (% of one core) during the run |
| `sched_lag_p95_ms` | How late readings went out compared with their schedule (above 0 = the system can't keep up) |

### PulseWatch: high-rate streaming to several viewers

N wearables stream samples (3-axis acceleration and heart rate) at a fixed rate to a hub. Several
viewers (a live chart, an anomaly detector, an archiver) each hold a `Watch()` stream and receive every
sample. The same `.proto` file runs over three transports:

- `grpb`: gRPB-M2M, typed calls and server streaming over MQTT, with the hub in its own process.
- `grpc`: plain gRPC over HTTP/2.
- `json`: the usual MQTT approach. Nodes publish JSON, viewers subscribe directly, there is no hub and no replies.

```sh
python -m grpb_examples.sim pulse --transport grpb --nodes 10 --hz 20 --viewers 3 --duration 60
python -m grpb_examples.sim pulse --transport grpb --flap 20:5      # 5 s total network outage at t=20 s
```

| Summary column | Meaning |
|---|---|
| `achieved_per_s` vs `offered_per_s` | Samples per second acknowledged vs attempted |
| `delivery_ratio`, `missing` | Share of acknowledged samples that every viewer received |
| `delay_p50/p95/p99/max_ms` | Sample created at the node until it arrived at a viewer (one shared clock) |
| `device_link_B_per_sample` | MQTT bytes on the node's link per sample (grpb includes the hub's reply; json has none) |
| `viewer_B_per_sample` | MQTT bytes on a viewer's link per sample received |
| `infra_cpu` (charts) | Hub + broker CPU together, so a design that moves work into the broker isn't flattered |
| `sample_pb_B`, `sample_json_B` | The same sample encoded as Protobuf and as JSON |
| `loopback_B_per_sample_all_hops` | Every byte on loopback per sample, TCP/IP included, all hops: comparable across transports |
| `recovery_ms` | With `--flap`: time from the network returning until the first acknowledged sample |

### SafeSwitch: commands while actuators fail

A building controller sends commands (open/close, lock/unlock) to 20 actuators every 0.5 s, each
with a 2 s deadline. Each actuator is a server, so the controller calls the device. The actuators
run in 4 processes, one per power circuit. Partway through the run, group 0 fails:

- `crash`: the process is killed, as in a power cut, then restarted.
- `freeze`: the process is stopped, as in a network partition with no clean disconnect, then resumed.
- `none`: no failure, as a baseline.

Every command an actuator carries out is written to disk with the time it was issued and the time it
ran. That shows whether a command was executed after the controller had already given up on it.

```sh
python -m grpb_examples.sim safeswitch --transport grpb --scenario crash
python -m grpb_examples.sim safeswitch --transport json --scenario freeze --keepalive 5
```

| Summary column | Meaning |
|---|---|
| `outage_fast_fail`, `outage_timed_out` | Commands to the failed group that failed at once vs waited the full deadline |
| `fails_fast_after_ms` | From the failure until commands start failing immediately ("never" = they keep timing out). Commands go out every `--period` s, so this is accurate to about one period |
| `controller_blocked_s` | Total controller time spent waiting on the failed group |
| `recovery_ms` | From restart/resume until the first successful command |
| `stale_executions`, `stale_max_late_s` | Commands executed more than the deadline after they were issued |
| `executed_but_reported_failed` | The controller recorded a failure, yet the actuator carried the command out |

The baselines are the usual alternatives. Plain gRPC needs the controller to reach every device
directly, which means no NAT and an open port per device. The JSON-over-MQTT baseline uses QoS 1 and a
persistent session, so no command is lost while the device is offline.

**What SafeSwitch found, and the fix.** In the first freeze runs, gRPB-M2M executed a few commands up
to 10 s late. Requests sent in the seconds before the broker noticed the frozen device sat in its
network buffer and ran when it resumed. Requests now carry their deadline as an absolute time too
(`Frame.deadline_unix_ms`), and `MqttServer` refuses any request that arrives after it
(`clock_skew_ms=500` by default, assuming NTP-synced clocks; `None` turns the check off). After the
fix, stale executions dropped to 0. `tests/test_mqtt_rpc.py::test_stale_request_is_refused_not_executed`
covers it.

**Topic aliases.** In PulseWatch, the gRPB-M2M topic strings (about 40 bytes each way) cost more
than Protobuf saved, and gRPB-M2M lost to JSON on bytes per sample. The library now uses MQTT 5 topic
aliases in both directions, which cut a sample from 162 to about 90 bytes, reply included. The JSON
baseline doesn't use aliases, because typical MQTT clients don't, but any MQTT 5 client could. FarmNet
uses the same `Onem2mClient` for all three formats, so there every format gets aliases and the
format comparison stays like for like.

## Network profiles

| Profile | netem settings (per hop, on loopback) |
|---|---|
| `lan` | none |
| `wifi` | delay 2 ms ± 1 ms, loss 0.5% |
| `4g` | delay 25 ms ± 10 ms, loss 1% |
| `constrained` | delay 50 ms ± 20 ms, loss 2%, rate 1 Mbit/s |
| `poor` | delay 100 ms ± 30 ms, loss 3%, rate 256 kbit/s |

On a single Pi every hop crosses loopback: node → broker, broker → CSE or hub, and back. Each hop
gets the delay, so a oneM2M request through ACME sees it four times. Absolute delays are therefore
pessimistic, but every format and transport is measured under exactly the same conditions. Any raw
netem string also works: `--netem "delay 40ms loss 1%"`.

## Output

Each run writes `results/<time>-<app>-<label>/`:

| File | Contents |
|---|---|
| `samples.csv` | One row per measured operation (reading, sample, delivery, command, execution) |
| `events.csv` | What the runner did and when: start, measuring, failure injected, restored, network down/up |
| `resources.csv` | CPU and memory of the simulator, broker, CSE and hub, once per second |
| `summary.csv` / `summary.md` | The headline numbers for this run |
| `env.json` | Machine, versions, network profile and the exact arguments |

A sweep (`python -m grpb_examples.sim sweep <app> --vary key=a,b -- <fixed args>`) adds `combined.csv`
(one row per run, with the varied settings) and `runs/`. `python -m grpb_examples.sim plot <dirs>` turns
sweeps into PNG charts. Add `--no-save` to any run to print the summary without writing files.

## Caveats

- **One machine.** All nodes share the Pi's CPU and clock. That makes the delay measurements exact,
  but nodes compete with the broker and CSE for CPU, so the CPU columns are reported with every run.
- **Python everywhere.** Protobuf encoding in Python costs more CPU than JSON (see the codec
  benchmark). On microcontrollers, with nanopb or C++, the ratio reverses. Byte counts don't depend on
  the language.
- **Baselines are fair but not identical.** The JSON-over-MQTT baseline in PulseWatch has no hub and
  no replies, so it does less work. That favours it on delay and CPU and is noted, not hidden.
- **Absolute deadlines need roughly synced clocks.** Use NTP on real devices, or set
  `clock_skew_ms=None` to rely on relative timeouts only.
