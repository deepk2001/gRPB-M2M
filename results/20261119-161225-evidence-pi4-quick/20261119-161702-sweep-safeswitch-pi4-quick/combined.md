## Sweep: safeswitch (pi4-quick)

| set_transport | set_scenario | set_netem | latency_p50_ms | outage_fast_fail | outage_timed_out | controller_blocked_s | fails_fast_after_ms | recovery_ms | stale_executions | stale_max_late_s | executed_but_reported_failed | error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpb | crash | lan | 45.17 | 60 | 0 | 0.0 | 252.202 | 797.079 | 0 | 0 | 0 |  |
| grpb | freeze | lan | 45.75 | 0 | 10 | 20.0 | never | 141.762 | 0 | 0 | 0 |  |
| grpb | none | lan | 45.685 |  |  |  |  |  | 0 | 0 | 0 |  |
| grpc | crash | lan | 2.06 | 60 | 0 | 0.0 | 250.934 | 3427.835 | 0 | 0 | 0 |  |
| grpc | freeze | lan | 2.06 | 0 | 10 | 20.0 | never | 17.5 | 0 | 0 | 0 |  |
| grpc | none | lan | 2.05 |  |  |  |  |  | 0 | 0 | 0 |  |
| json | crash | lan | 24.755 | 0 | 15 | 30.0 | never | 576.806 | 15 | 6.45 | 15 |  |
| json | freeze | lan | 24.76 | 0 | 10 | 20.0 | never | 119.727 | 10 | 5.93 | 10 |  |
| json | none | lan | 24.775 |  |  |  |  |  | 0 | 0 | 0 |  |
