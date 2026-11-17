## farmnet: formatcbor-nodes50-netemlan-r0

| format | nodes | network | readings/s | errors | device B/reading | notify B | fleet MB/day | RTT p50 ms | p95 | notify p95 ms | JSON reads ok | CSE CPU % | broker CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cbor | 50 | lan | 10.00 | 0 | 623.50 | 432.70 | 538.67 | 3.77 | 6.50 | 8.01 | 10 | 7.80 | 0.20 |

device B/reading = exact MQTT PUBLISH bytes of request + response on the device's own link (topics and properties included, PUBACKs excluded). fleet MB/day projects that over 24 h at this interval. JSON reads ok = containers read back over HTTP as JSON matching what the device wrote.
