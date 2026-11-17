## farmnet: formatcbor-nodes200-netemlan-r0

| format | nodes | network | readings/s | errors | device B/reading | notify B | fleet MB/day | RTT p50 ms | p95 | notify p95 ms | JSON reads ok | CSE CPU % | broker CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cbor | 200 | lan | 40.00 | 0 | 555.70 | 398.30 | 1920.47 | 2.80 | 12.03 | 13.66 | 10 | 31.90 | 0.30 |

device B/reading = exact MQTT PUBLISH bytes of request + response on the device's own link (topics and properties included, PUBACKs excluded). fleet MB/day projects that over 24 h at this interval. JSON reads ok = containers read back over HTTP as JSON matching what the device wrote.
