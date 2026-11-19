## pulse: transportjson-hz5-netemwifi-r0

| transport | nodes | Hz | viewers | network | samples/s | errors | delivered | delay p50 ms | p95 | p99 | device B/sample | pb B | JSON B | hub CPU % | sim CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| json | 10 | 5.00 | 3 | wifi | 49.90 | 0 | 1.00 | 7.87 | 124.97 | 217.14 | 134.50 | 37 | 103 |  | 19.90 |

delay = sample creation at the node to arrival at a viewer (one Pi clock). delivered = share of acknowledged samples every viewer received. device B/sample = exact MQTT bytes on the node's own link per sample, including the hub's reply for grpb (json has no reply, only a PUBACK, not counted); HTTP/2 framing isn't visible to the app, so grpc shows only loopback bytes in summary.csv.
