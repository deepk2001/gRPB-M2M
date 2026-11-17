## farmnet: formatjson-nodes50-netemlan-r0

| format | nodes | network | readings/s | errors | device B/reading | notify B | fleet MB/day | RTT p50 ms | p95 | notify p95 ms | JSON reads ok | CSE CPU % | broker CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| json | 50 | lan | 10.00 | 0 | 730.40 | 546.70 | 631.06 | 5.62 | 9.64 | 10.72 | 10 | 9.90 | 0.20 |

device B/reading = exact MQTT PUBLISH bytes of request + response on the device's own link (topics and properties included, PUBACKs excluded). fleet MB/day projects that over 24 h at this interval. JSON reads ok = containers read back over HTTP as JSON matching what the device wrote.
