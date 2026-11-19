## Sweep: pulse (pi4-quick)

| set_transport | set_hz | set_netem | achieved_per_s | publish_errors | delivery_ratio | delay_p50_ms | delay_p95_ms | delay_p99_ms | device_link_B_per_sample | hub_cpu_mean | error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpb | 10 | lan | 100.0 | 0 | 1.0 | 37.907 | 64.381 | 83.701 | 126.8 | 36.1 |  |
| grpb | 40 | lan | 109.5 | 0 | 1.0 | 74.174 | 105.702 | 124.86 | 127.4 | 39.2 |  |
| grpc | 10 | lan | 100.0 | 0 | 1.0 | 2.542 | 4.775 | 5.268 |  | 32.4 |  |
| grpc | 40 | lan | 399.7 | 0 | 1.0 | 4.342 | 8.414 | 10.726 |  | 105.8 |  |
| json | 10 | lan | 100.0 | 0 | 1.0 | 2.129 | 4.697 | 5.998 | 134.3 |  |  |
| json | 40 | lan | 399.9 | 0 | 0.76141 | 2813.088 | 3891.247 | 3956.216 | 134.5 |  |  |
