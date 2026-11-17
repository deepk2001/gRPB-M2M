## Sweep: safeswitch (laptop-quick)

| set_transport | set_scenario | set_netem | latency_p50_ms | outage_fast_fail | outage_timed_out | controller_blocked_s | fails_fast_after_ms | recovery_ms | stale_executions | stale_max_late_s | executed_but_reported_failed | error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpb | crash | lan | 1.95 | 58 | 0 | 0.8 | 257.96 | 504.329 | 0 | 0 | 0 |  |
| grpb | freeze | lan | 2.12 | 0 | 10 | 20.0 | never | 9.21 | 0 | 0 | 0 |  |
| grpb | none | lan | 2.02 |  |  |  |  |  | 0 | 0 | 0 |  |
| grpc | crash | lan | 1.11 | 59 | 0 | 0.0 | 5.471 | 4503.683 | 0 | 0 | 0 |  |
| grpc | freeze | lan | 1.14 | 0 | 10 | 20.0 | never | 6.4 | 1 | 2.0 | 0 |  |
| grpc | none | lan | 1.19 |  |  |  |  |  | 0 | 0 | 0 |  |
| json | crash | lan | 1.82 | 0 | 15 | 30.1 | never | 100.765 | 15 | 6.1 | 15 |  |
| json | freeze | lan | 1.515 | 0 | 7 | 14.0 | never | 6.325 | 8 | 6.0 | 11 |  |
| json | none | lan | 2.71 |  |  |  |  |  | 0 | 0 | 0 |  |
