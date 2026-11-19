## Sweep: safeswitch (pi4)

| set_transport | set_scenario | set_netem | latency_p50_ms | outage_fast_fail | outage_timed_out | controller_blocked_s | fails_fast_after_ms | recovery_ms | stale_executions | stale_max_late_s | executed_but_reported_failed | error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpb | crash | lan | 46.02 | 150 | 0 | 0.0 | 252.204 | 795.726 | 0 | 0 | 0 |  |
| grpb | crash | wifi | 59.135 | 150 | 0 | 0.0 | 249.559 | 935.7 | 0 | 0 | 0 |  |
| grpb | freeze | lan | 44.35 | 79 | 15 | 35.5 | 7073.934 | 1432.495 | 0 | 0 | 0 |  |
| grpb | freeze | wifi | 58.965 | 78 | 15 | 36.0 | 7432.109 | 1484.584 | 0 | 0 | 0 |  |
| grpb | none | lan | 45.365 |  |  |  |  |  | 0 | 0 | 0 |  |
| grpb | none | wifi | 59.195 |  |  |  |  |  | 0 | 0 | 0 |  |
| grpc | crash | lan | 2.05 | 150 | 0 | 0.1 | 250.944 | 2752.462 | 0 | 0 | 0 |  |
| grpc | crash | wifi | 6.2 | 150 | 0 | 0.1 | 255.833 | 2889.675 | 0 | 0 | 0 |  |
| grpc | freeze | lan | 2.04 | 0 | 35 | 70.1 | never | 66.401 | 0 | 0 | 0 |  |
| grpc | freeze | wifi | 6.315 | 0 | 35 | 70.1 | never | 33.724 | 0 | 0 | 0 |  |
| grpc | none | lan | 2.05 |  |  |  |  |  | 0 | 0 | 0 |  |
| grpc | none | wifi | 6.25 |  |  |  |  |  | 0 | 0 | 0 |  |
| json | crash | lan | 24.79 | 0 | 35 | 70.0 | never | 625.128 | 35 | 15.46 | 35 |  |
| json | crash | wifi | 41.1 | 0 | 35 | 70.0 | never | 875.863 | 35 | 15.48 | 35 |  |
| json | freeze | lan | 24.83 | 0 | 36 | 72.0 | never | 1112.845 | 45 | 15.95 | 46 |  |
| json | freeze | wifi | 42.795 | 0 | 36 | 72.0 | never | 1105.046 | 55 | 15.96 | 56 |  |
| json | none | lan | 23.42 |  |  |  |  |  | 0 | 0 | 0 |  |
| json | none | wifi | 45.125 |  |  |  |  |  | 0 | 0 | 0 |  |
