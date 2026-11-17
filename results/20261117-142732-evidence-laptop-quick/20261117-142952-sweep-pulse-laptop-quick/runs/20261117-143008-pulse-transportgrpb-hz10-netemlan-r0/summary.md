## pulse: transportgrpb-hz10-netemlan-r0

| transport | nodes | Hz | viewers | network | samples/s | errors | delivered | delay p50 ms | p95 | p99 | device B/sample | pb B | JSON B | hub CPU % | sim CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpb | 10 | 10.00 | 3 | lan | 100.00 | 0 | 1.00 | 1.51 | 3.37 | 21.72 | 161.90 | 37 | 107 | 9.70 | 16.50 |

delay = sample creation at the node to arrival at a viewer (one Pi clock). delivered = share of acknowledged samples every viewer received. device B/sample = exact MQTT bytes on the node's own link per sample, including the hub's reply for grpb (json has no reply, only a PUBACK, not counted); HTTP/2 framing isn't visible to the app, so grpc shows only loopback bytes in summary.csv.
