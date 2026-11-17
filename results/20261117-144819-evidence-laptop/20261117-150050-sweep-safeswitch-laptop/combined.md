## Sweep: safeswitch (laptop)

| set_transport | set_scenario | set_netem | latency_p50_ms | outage_fast_fail | outage_timed_out | controller_blocked_s | fails_fast_after_ms | recovery_ms | stale_executions | stale_max_late_s | executed_but_reported_failed | error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpb | crash | lan | 1.74 | 150 | 0 | 0.0 | 247.816 | 388.651 | 0 | 0 | 0 |  |
| grpb | freeze | lan | 1.75 | 80 | 15 | 35.4 | 7018.924 | 1409.764 | 0 | 0 | 0 |  |
| grpb | none | lan | 1.75 |  |  |  |  |  | 0 | 0 | 0 |  |
| grpc | crash | lan | 1.175 | 150 | 0 | 0.1 | 245.062 | 1424.345 | 0 | 0 | 0 |  |
| grpc | freeze | lan | 1.26 | 0 | 35 | 70.2 | never | 7.876 | 0 | 0 | 0 |  |
| grpc | none | lan | 1.23 |  |  |  |  |  | 0 | 0 | 0 |  |
| json | crash | lan | 1.03 | 0 | 35 | 70.1 | never | 96.766 | 35 | 15.49 | 35 |  |
| json | freeze | lan | 1.04 | 0 | 35 | 70.1 | never | 1017.399 | 45 | 15.94 | 45 |  |
| json | none | lan | 0.97 |  |  |  |  |  | 0 | 0 | 0 |  |
