// Builds the gRPB-M2M benefits report (.docx) from data.json (see extract.py).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, HeadingLevel, LevelFormat, BorderStyle, Footer, PageNumber, TabStopType,
} = require("docx");

const D = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const OUT = process.argv[3];

// ---------- data helpers ----------
const n = (v) => (v === "" || v === undefined || v === null ? NaN : Number(v));
const same = (a, b) => (!isNaN(n(a)) && !isNaN(n(b)) ? n(a) === n(b) : String(a) === String(b));
const pick = (rows, cond) => rows.find((r) => Object.entries(cond).every(([k, v]) => same(r[k], v)));
const f0 = (v) => (isNaN(n(v)) ? String(v) : Math.round(n(v)).toLocaleString("en-US"));
const f1 = (v) => (isNaN(n(v)) ? String(v) : n(v).toFixed(1));
const f2 = (v) => (isNaN(n(v)) ? String(v) : n(v).toFixed(2));
const ratio = (a, b) => (n(a) / n(b)).toFixed(2) + "×";
const sec = (ms) => (isNaN(n(ms)) ? String(ms) : (n(ms) / 1000).toFixed(n(ms) < 10000 ? 2 : 1) + " s");

const maxNodes = Math.max(...D.farmnet.map((r) => n(r.nodes)));
const fm = Object.fromEntries(["json", "cbor", "pb"].map((f) => [f, pick(D.farmnet, { format: f, nodes: maxNodes, netem: "lan" })]));
const maxHz = Math.max(...D.pulse.map((r) => n(r.hz)));
const pu = Object.fromEntries(["grpb", "grpc", "json"].map((t) => [t, pick(D.pulse, { transport: t, hz: maxHz, netem: "lan" })]));
const infra = (r) => (n(r.hub_cpu_mean) || 0) + (n(r.broker_cpu_mean) || 0);
const ss = (t, s, net = "lan") => pick(D.safeswitch, { transport: t, scenario: s, netem: net });
const codec = Object.fromEntries(D.codec.map((r) => [r.format, r]));
const onPi = /raspberry/i.test(D.device_model || "");
const nets = [...new Set(D.farmnet.map((r) => r.netem))];
const emulated = nets.filter((x) => x !== "lan");
const machineName = onPi ? D.device_model : D.machine;
const longDate = new Date((D.date || "2026-11-17") + "T12:00:00").toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
const interopAll = D.farmnet.every((r) => r.interop_ok === r.interop_checked);
const farmErrors = D.farmnet.reduce((a, r) => a + n(r.errors), 0);
const pulseErrors = D.pulse.reduce((a, r) => a + n(r.publish_errors), 0);
const pulseDelivery = Math.min(...D.pulse.map((r) => n(r.delivery_ratio)));

// ---------- styling helpers ----------
const FONT = "Arial";
const BLUE = "1F4E9A";
const GREY = "5B6475";
const W = 9360; // content width, US Letter with 1" margins
const border = { style: BorderStyle.SINGLE, size: 4, color: "D5D9E0" };
const borders = { top: border, bottom: border, left: border, right: border };

const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120, line: 276 }, ...opts,
  children: (Array.isArray(text) ? text : [text]).map((t) => (typeof t === "string" ? new TextRun(t) : t)) });
const b = (t) => new TextRun({ text: t, bold: true });
const i = (t) => new TextRun({ text: t, italics: true });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const bullet = (parts) => p(parts, { numbering: { reference: "bullets", level: 0 }, spacing: { after: 60, line: 276 } });
const code = (t) => new Paragraph({ spacing: { after: 0 }, shading: { fill: "F3F4F6", type: ShadingType.CLEAR },
  children: [new TextRun({ text: t, font: "Courier New", size: 18 })] });
const caption = (t) => p([new TextRun({ text: t, italics: true, color: GREY, size: 18 })], { spacing: { after: 240 } });

function table(head, body, widths, opts = {}) {
  const total = widths.reduce((a, c) => a + c, 0);
  const cell = (txt, isHead, col, row) => new TableCell({
    borders, width: { size: widths[col], type: WidthType.DXA },
    shading: isHead ? { fill: "E8EDF5", type: ShadingType.CLEAR }
      : (opts.highlightCol === col ? { fill: "EEF4FF", type: ShadingType.CLEAR } : undefined),
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ alignment: col > 0 && !opts.leftAll ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: [new TextRun({ text: String(txt), bold: isHead || (opts.boldFirst && col === 0), size: 19 })] })],
  });
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: head.map((t, c) => cell(t, true, c)) }),
      ...body.map((r, ri) => new TableRow({ children: r.map((t, c) => cell(t, false, c, ri)) }))],
  });
}
const gap = () => new Paragraph({ spacing: { after: 160 }, children: [] });

function chart(name, cap) {
  const c = D.charts[name];
  if (!c) return [p(i(`(chart ${name} not found)`))];
  const [w, hgt] = c.size;
  const width = w / hgt > 2.2 ? 600 : 470; // wide charts full width, others about 5 in
  return [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
    children: [new ImageRun({ type: "png", data: fs.readFileSync(c.path),
      transformation: { width, height: Math.round(width * hgt / w) },
      altText: { title: cap, description: cap, name } })] }), caption(cap)];
}

// ---------- content ----------
const pbVsJson = ratio(fm.pb.device_link_B_per_reading, fm.json.device_link_B_per_reading);
const pbVsCbor = ratio(fm.pb.device_link_B_per_reading, fm.cbor.device_link_B_per_reading);
const pulseVsJson = ratio(pu.grpb.device_link_B_per_sample, pu.json.device_link_B_per_sample);
const hzs = [...new Set(D.pulse.map((r) => n(r.hz)))].sort((a, b) => a - b);
const at = (t, hz, net = "lan") => pick(D.pulse, { transport: t, hz, netem: net });
const dDelay = hzs.map((hz) => n(at("grpb", hz).delay_p95_ms) - n(at("grpc", hz).delay_p95_ms));
const delayRange = `${Math.min(...dDelay).toFixed(1)} to ${Math.max(...dDelay).toFixed(1)} ms`;
const cpuAt = (t) => hzs.map((hz) => f0(infra(at(t, hz)))).join(" / ");
const rates = hzs.map((hz) => f0(n(at("grpb", hz).offered_per_s))).join(" / ");

const children = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("gRPB-M2M: Measured Benefits")] }),
  p([new TextRun({ text: `Team Nittany Nerds · ESTIMED oneM2M Hackathon #2 · ${longDate}`, color: GREY })],
    { spacing: { after: 240 } }),

  p([b(`gRPB-M2M makes oneM2M traffic smaller and device commands safer than the alternatives, at the cost of ${delayRange} of extra delay on a local network. `),
    `Protobuf inside oneM2M carries a sensor reading in ${pbVsJson} the bytes of JSON and ${pbVsCbor} the bytes of CBOR, and existing JSON clients still read the data unchanged. `,
    `When devices crash or lose their network, gRPB-M2M never carried out a command after the controller had given up on it, while the usual JSON-over-MQTT setup did so ${f0(ss("json", "crash").stale_executions)} to ${f0(ss("json", "freeze").stale_executions)} times per run, up to ${f0(ss("json", "freeze").stale_max_late_s)} s late.`]),
  p([i(onPi
    ? `These results come from a ${D.device_model} with every node simulated on the Pi itself${emulated.length ? `, on its local network and under emulated ${emulated.join(", ")} links` : ""}. Headline numbers are from the local-network runs; section 4 shows the emulated networks.`
    : "These results come from a laptop with every node simulated on one machine and no emulated network. The same commands run on the Raspberry Pi with emulated Wi-Fi, 4G and constrained links (make evidence); those numbers will replace these before submission.")]),

  h1("Results at a glance"),
  table(["Claim", "gRPB-M2M", "Compared with"], [
    [`Bytes per reading in oneM2M (${maxNodes} sensors)`, `${f0(fm.pb.device_link_B_per_reading)} B`,
      `JSON ${f0(fm.json.device_link_B_per_reading)} B, CBOR ${f0(fm.cbor.device_link_B_per_reading)} B`],
    [`Fleet data per day (${maxNodes} sensors, one reading every 5 s)`, `${f0(n(fm.pb.fleet_MB_per_day))} MB`,
      `JSON ${f0(fm.json.fleet_MB_per_day)} MB, CBOR ${f0(fm.cbor.fleet_MB_per_day)} MB`],
    ["Protobuf data readable by JSON clients over HTTP", interopAll ? "every check passed" : "see FarmNet", "standard oneM2M"],
    ["Stale commands after a crash / a freeze", `${f0(ss("grpb", "crash").stale_executions)} / ${f0(ss("grpb", "freeze").stale_executions)}`,
      `JSON over MQTT ${f0(ss("json", "crash").stale_executions)} / ${f0(ss("json", "freeze").stale_executions)}; gRPC ${f0(ss("grpc", "crash").stale_executions)} / ${f0(ss("grpc", "freeze").stale_executions)}`],
    ["Controller time stuck during a 15 s network partition", `${f1(ss("grpb", "freeze").controller_blocked_s)} s`,
      `gRPC ${f1(ss("grpc", "freeze").controller_blocked_s)} s, JSON over MQTT ${f1(ss("json", "freeze").controller_blocked_s)} s`],
    ["Recovery after an actuator restarts", sec(ss("grpb", "crash").recovery_ms),
      `gRPC ${sec(ss("grpc", "crash").recovery_ms)}; JSON over MQTT ${sec(ss("json", "crash").recovery_ms)} (by replaying stale commands)`],
    [`Bytes per streamed sample, reply included (${maxHz} Hz)`, `${f0(pu.grpb.device_link_B_per_sample)} B`,
      `JSON over MQTT ${f0(pu.json.device_link_B_per_sample)} B with no reply`],
    [`Hub + broker CPU, % of a core, at ${rates} samples/s`, cpuAt("grpb"), `gRPC hub ${cpuAt("grpc")} (mixed)`],
    [`Sensor-to-viewer delay, 95th percentile (${maxHz} Hz)`, `${f1(pu.grpb.delay_p95_ms)} ms`,
      `gRPC ${f1(pu.grpc.delay_p95_ms)} ms, JSON over MQTT ${f1(pu.json.delay_p95_ms)} ms (trade-off)`],
  ], [3700, 2060, 3600], { boldFirst: false }),
  gap(),

  h1("How we measured"),
  p("Three mock applications run many simulated devices on one machine. Each device has its own MQTT connection and identity, and every measured operation is saved as a row in a CSV file, so any number here can be traced back to raw data."),
  table(["Application", "What it simulates", "Compared"], [
    ["FarmNet", `Up to ${maxNodes} farm sensors, each a oneM2M AE writing a reading every 5 s to the patched ACME CSE; an alert service receives every reading as a notification; a JSON client reads the data back over HTTP`, "Protobuf, CBOR and JSON, all through the same client"],
    ["PulseWatch", `10 wearables streaming at up to ${maxHz} samples/s to a hub; 3 viewers hold live streams`, "gRPB-M2M, gRPC over HTTP/2, plain JSON over MQTT"],
    ["SafeSwitch", "A controller commanding 20 actuators every 0.5 s with a 2 s deadline; one group of 5 is killed (crash) or frozen (network partition) for 15 s", "gRPB-M2M, gRPC over HTTP/2, JSON over MQTT with a persistent session"],
  ], [1500, 5060, 2800], { leftAll: true, boldFirst: true }),
  gap(),
  p([`Setup: ${machineName}, ${D.cpus} CPU cores, Python ${D.python}, Mosquitto 2.1, ACME 2026.05.1 with our Protobuf patch. Runs lasted 30 s after a warm-up, one run per setting. Byte counts are exact MQTT packet sizes measured on each device's own connection; they don't depend on the machine. Timings and CPU do, and need the Raspberry Pi run to be final.`]),

  h1("1. Smaller messages inside oneM2M (FarmNet)"),
  p([`Protobuf cuts the bytes on each sensor's link to ${pbVsJson} of JSON and ${pbVsCbor} of CBOR, and the saving is the same at every fleet size. `,
    `Across ${maxNodes} sensors that is ${f0(fm.pb.fleet_MB_per_day)} MB a day instead of ${f0(fm.json.fleet_MB_per_day)} MB with JSON, a difference of ${f0(n(fm.json.fleet_MB_per_day) - n(fm.pb.fleet_MB_per_day))} MB a day on metered links.`]),
  ...chart("farmnet_bytes", "Figure 1. MQTT bytes on a sensor's link per reading (request and response, topics and properties included)."),
  table(["Format", "Bytes / reading", "vs JSON", "Notification bytes", "Fleet MB / day", "RTT p50 ms", "RTT p95 ms", "CSE CPU %"],
    ["json", "cbor", "pb"].map((f) => [f === "pb" ? "Protobuf" : f.toUpperCase(), f0(fm[f].device_link_B_per_reading),
      ratio(fm[f].device_link_B_per_reading, fm.json.device_link_B_per_reading), f0(fm[f].notify_B), f0(fm[f].fleet_MB_per_day),
      f1(fm[f].rtt_p50_ms), f1(fm[f].rtt_p95_ms), f1(fm[f].cse_cpu_mean)]),
    [1300, 1250, 900, 1350, 1250, 1100, 1100, 1110], { boldFirst: true }),
  caption(`Table 1. FarmNet at ${maxNodes} sensors. ${farmErrors} errors across all FarmNet runs.`),
  p([b("It stays standard oneM2M. "), interopAll
    ? "In every run, containers written in Protobuf over MQTT were read back over HTTP as JSON by an ordinary client, and matched exactly what the device wrote. Existing dashboards keep working."
    : "Some interoperability checks failed; see the run data."]),
  p([b("The cost is CPU in the CSE. "), `With ${maxNodes} sensors the CSE used ${f1(fm.pb.cse_cpu_mean)}% of a core for Protobuf against ${f1(fm.json.cse_cpu_mean)}% for JSON, because Python's JSON library is faster than its Protobuf one ${codec.pb && codec.json ? ` (codec benchmark: ${f1(codec.pb.median_encode_us)} µs vs ${f1(codec.json.median_encode_us)} µs to encode a primitive)` : ""}. On a local network the round trip doesn't show the size advantage either: the network isn't the bottleneck there. The emulated constrained links on the Pi are where smaller messages should also mean lower delay.`]),
  ...chart("farmnet_fleet_mb_day", "Figure 2. Projected data per day for the whole fleet, by fleet size."),

  h1("2. Safe commands when devices fail (SafeSwitch)"),
  p([`A command that runs after the controller has given up is dangerous: a door that unlocks 15 seconds late, a valve that opens after the operator was told it failed. `,
    b(`gRPB-M2M carried out no stale commands in any scenario. `),
    `JSON over MQTT with a persistent session, the common way to avoid losing commands, carried out ${f0(ss("json", "crash").stale_executions)} after a crash and ${f0(ss("json", "freeze").stale_executions)} after a freeze, up to ${f0(ss("json", "freeze").stale_max_late_s)} s late, and every one had been reported to the controller as failed.`]),
  ...chart("safeswitch_stale", "Figure 3. Commands carried out after the controller had already given up on them."),
  table(["Transport", "Scenario", "Fast fails", "Timed out", "Controller stuck", "Fails fast after", "Recovery", "Stale"],
    ["grpb", "grpc", "json"].flatMap((t) => ["crash", "freeze"].map((s) => {
      const r = ss(t, s);
      return [{ grpb: "gRPB-M2M", grpc: "gRPC", json: "JSON/MQTT" }[t], s, f0(r.outage_fast_fail), f0(r.outage_timed_out),
        `${f1(r.controller_blocked_s)} s`, r.fails_fast_after_ms === "never" ? "never" : sec(r.fails_fast_after_ms),
        sec(r.recovery_ms), f0(r.stale_executions)];
    })), [1350, 950, 1050, 1050, 1350, 1300, 1150, 1160], { boldFirst: true }),
  caption("Table 2. Commands to the failed group during a 15 s outage. Commands go out every 0.5 s, so \"fails fast after\" is accurate to about 0.5 s."),
  p([b("Dead devices are noticed, so the controller doesn't hang. "),
    `When a device is cut off without a clean disconnect (freeze), the broker's keepalive and the device's Last Will mark it offline after about ${sec(ss("grpb", "freeze").fails_fast_after_ms)} (1.5 × the 5 s keepalive). From then on, calls fail immediately. gRPC and JSON over MQTT never noticed, and waited out the full deadline on every command: the controller was stuck ${f1(ss("grpc", "freeze").controller_blocked_s)} s against ${f1(ss("grpb", "freeze").controller_blocked_s)} s for gRPB-M2M.`]),
  ...chart("safeswitch_blocked", "Figure 4. Total controller time spent waiting on the failed actuators."),
  p([b("Recovery. "), `After a crash and restart, gRPB-M2M was working again in ${sec(ss("grpb", "crash").recovery_ms)}, against ${sec(ss("grpc", "crash").recovery_ms)} for gRPC, which backs off between reconnect attempts. JSON over MQTT recovered fastest (${sec(ss("json", "crash").recovery_ms)}), by replaying the stale commands. After a freeze, gRPC recovered faster (${sec(ss("grpc", "freeze").recovery_ms)} vs ${sec(ss("grpb", "freeze").recovery_ms)}) because its connection never dropped, which is also why it never detected the outage.`]),

  h1("3. Streaming to several viewers (PulseWatch)"),
  p([`Every transport kept up with ${f0(pu.grpb.offered_per_s)} samples a second; viewers received ${pulseDelivery === 1 ? "every" : (pulseDelivery * 100).toFixed(2) + "% of"} acknowledged sample with ${pulseErrors} errors. `,
    `gRPB-M2M sends ${f0(pu.grpb.device_link_B_per_sample)} B per sample on the sensor's link, reply included: ${pulseVsJson} of plain JSON over MQTT (${f0(pu.json.device_link_B_per_sample)} B), which gets no reply at all. Each viewer receives ${f0(pu.grpb.viewer_B_per_sample)} B per sample against ${f0(pu.json.viewer_B_per_sample)} B.`]),
  ...chart("pulse_bytes", "Figure 5. MQTT bytes per sample on a sensor's link and on a viewer's link. gRPC's HTTP/2 framing isn't visible to the application."),
  p([b("CPU is mixed. "), `Counting the hub and the broker together, gRPB-M2M used ${cpuAt("grpb")}% of a core at ${rates} samples a second, against ${cpuAt("grpc")}% for the gRPC hub. gRPB-M2M costs more at low rates and less at the highest one, where it grows more slowly. Plain JSON over MQTT uses the least (${cpuAt("json")}%): it has no hub and sends no replies, so it does much less work.`]),
  ...chart("pulse_infra_cpu", "Figure 6. Infrastructure CPU: hub plus broker, so moving work into the broker isn't counted as a saving."),
  p([b("The trade-off is delay. "), `Every message passes through the broker, so the 95th-percentile delay from sensor to viewer was ${f1(pu.grpb.delay_p95_ms)} ms against ${f1(pu.grpc.delay_p95_ms)} ms for gRPC and ${f1(pu.json.delay_p95_ms)} ms for JSON over MQTT. The broker hop is what lets the hub reach devices behind NAT and mobile networks without opening ports on them, which gRPC can't do.`]),
  ...chart("pulse_delay_p95", "Figure 7. Sensor-to-viewer delay, 95th percentile, by sample rate."),

  ...networkSection(),

  h1(`${emulated.length ? 5 : 4}. What the measurements changed in the framework`),
  p("Running the simulations exposed two weaknesses. Both are fixed, tested, and measured again."),
  table(["Finding", "Fix", "Before", "After"], [
    ["After a network partition, a device executed commands that had sat in its network buffer, up to 10 s late",
      "Requests carry an absolute deadline; servers refuse requests that arrive after it (clock tolerance 500 ms)", "4 stale commands", `${f0(ss("grpb", "freeze").stale_executions)} stale commands`],
    ["Topic strings (about 40 B each way) cost more than Protobuf saved: gRPB-M2M lost to JSON on bytes per streamed sample",
      "MQTT 5 topic aliases in both directions: a 2-byte number replaces the topic after the first message", "162 B per sample", `${f0(pu.grpb.device_link_B_per_sample)} B per sample`],
    ["Same topic overhead on every oneM2M request", "Same aliases in the oneM2M client", "462 B per reading", `${f0(fm.pb.device_link_B_per_reading)} B per reading`],
  ], [3100, 3460, 1400, 1400], { leftAll: true }),
  caption("Table 3. \"Before\" values come from development runs on the same laptop with the same settings."),
  p("The library also gained exact traffic counters (channel.stats() and server.stats()), which these measurements use. 79 automated tests cover the library, the ACME integration and the three simulations."),

  h1(`${emulated.length ? 6 : 5}. Trade-offs and open items`),
  bullet([b("Delay: "), `${delayRange} more than gRPC at the 95th percentile on a local network, from the broker hop.`]),
  bullet([b("CPU: "), "more than gRPC at low message rates, less at the highest; plain JSON over MQTT does less work than either."]),
  bullet([b("CPU in Python: "), "Protobuf encoding is slower than JSON in Python, so the CSE uses more CPU. C or C++ devices and a compiled codec would reverse this; byte counts don't depend on the language."]),
  bullet([b("Clocks: "), "refusing stale requests assumes device clocks agree to within 500 ms (NTP). The check can be relaxed or turned off."]),
  bullet([b("Baselines: "), "JSON over MQTT in PulseWatch sends no replies, and doesn't use topic aliases, as is typical. An MQTT 5 client could add aliases to JSON too; Protobuf's saving on the payload itself (37 B vs 106 B per sample) would remain."]),
  ...(onPi && emulated.length ? [] : [bullet([b("Not yet measured: "), "the Raspberry Pi itself, and emulated Wi-Fi, 4G and constrained links. Those runs are scripted and are the next step."])]),

  h1(`${emulated.length ? 7 : 6}. Reproducing these results`),
  p("From the repository on a laptop or Raspberry Pi:"),
  code("make setup                                   # or make setup-pi"),
  code("make broker                                  # terminal 1"),
  code("make cse ARGS=\"--headless --log-level warn\"  # terminal 2"),
  code("make evidence                                # terminal 3: all runs, then charts"),
  gap(),
  p([`This report's data: ${D.evidence_dir}/ (one folder per sweep with combined.csv, one folder per run with samples.csv, events.csv, resources.csv, summary.csv and env.json, and charts/). docs/SIMULATIONS.md defines every metric.`]),
];

function networkSection() {
  if (!emulated.length) return [];
  const midNodes = [...new Set(D.farmnet.map((r) => n(r.nodes)))].sort((a, b) => a - b)[1] ?? maxNodes;
  const midHz = hzs[Math.min(1, hzs.length - 1)];
  const farmRows = nets.flatMap((net) => ["json", "cbor", "pb"].map((f) => {
    const r = pick(D.farmnet, { format: f, nodes: midNodes, netem: net });
    return r ? [net, f === "pb" ? "Protobuf" : f.toUpperCase(), f1(r.rtt_p50_ms), f1(r.rtt_p95_ms), f1(r.notify_p95_ms), f0(r.errors), f1(r.sched_lag_p95_ms)] : null;
  })).filter(Boolean);
  const pulseRows = nets.flatMap((net) => ["grpb", "grpc", "json"].map((t) => {
    const r = at(t, midHz, net);
    return r ? [net, { grpb: "gRPB-M2M", grpc: "gRPC", json: "JSON/MQTT" }[t], f1(r.achieved_per_s), f2(r.delivery_ratio), f1(r.delay_p50_ms), f1(r.delay_p95_ms), f0(r.publish_errors)] : null;
  })).filter(Boolean);
  const ssNets = [...new Set(D.safeswitch.map((r) => r.netem))].filter((x) => x !== "lan");
  const ssRows = ssNets.flatMap((net) => ["grpb", "grpc", "json"].flatMap((t) => ["crash", "freeze"].map((s) => {
    const r = ss(t, s, net);
    return r ? [net, { grpb: "gRPB-M2M", grpc: "gRPC", json: "JSON/MQTT" }[t], s, `${f1(r.controller_blocked_s)} s`, sec(r.recovery_ms), f0(r.stale_executions)] : null;
  }))).filter(Boolean);
  return [
    h1("4. Under emulated networks"),
    p(`The same runs under emulated links (tc netem on loopback; every hop gets the delay and loss, see docs/SIMULATIONS.md): ${emulated.join(", ")}. Bytes don't change with the network; delay, loss and throughput do.`),
    table(["Network", "Format", "RTT p50 ms", "RTT p95 ms", "Notify p95 ms", "Errors", "Sched. lag p95 ms"], farmRows,
      [1400, 1300, 1300, 1300, 1400, 1100, 1560], { boldFirst: true }),
    caption(`Table 4. FarmNet with ${midNodes} sensors under each network.`),
    ...chart("farmnet_rtt_p95", "Figure 8. FarmNet round trip, 95th percentile, by fleet size and network."),
    table(["Network", "Transport", "Samples/s", "Delivered", "Delay p50 ms", "Delay p95 ms", "Errors"], pulseRows,
      [1400, 1500, 1300, 1200, 1350, 1350, 1260], { boldFirst: true }),
    caption(`Table 5. PulseWatch at ${midHz} samples/s per node under each network.`),
    ...chart("pulse_delay_p95", "Figure 9. PulseWatch delay, 95th percentile, by rate and network."),
    ...(ssRows.length ? [table(["Network", "Transport", "Scenario", "Controller stuck", "Recovery", "Stale"], ssRows,
      [1500, 1600, 1300, 1700, 1600, 1660], { boldFirst: true }), caption("Table 6. SafeSwitch under an emulated network.")] : []),
  ];
}

const doc = new Document({
  creator: "Nittany Nerds", title: "gRPB-M2M: Measured Benefits",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 44, bold: true, color: "1D2433" }, paragraph: { spacing: { before: 0, after: 80 }, keepNext: true } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: BLUE }, paragraph: { spacing: { before: 320, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "1D2433" }, paragraph: { spacing: { before: 240, after: 100 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: W }],
      children: [new TextRun({ text: "gRPB-M2M: Measured Benefits", color: GREY, size: 16 }),
        new TextRun({ children: ["\tPage ", PageNumber.CURRENT], color: GREY, size: 16 })] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote " + OUT); });
