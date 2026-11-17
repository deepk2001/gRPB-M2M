## farmnet: formatjson-nodes200-netemlan-r0

| format | nodes | network | readings/s | errors | device B/reading | notify B | fleet MB/day | RTT p50 ms | p95 | notify p95 ms | JSON reads ok | CSE CPU % | broker CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| json | 200 | lan | 40.00 | 0 | 731.70 | 547.30 | 2528.73 | 2.58 | 11.06 | 11.77 | 10 | 27.00 | 0.40 |

device B/reading = exact MQTT PUBLISH bytes of request + response on the device's own link (topics and properties included, PUBACKs excluded). fleet MB/day projects that over 24 h at this interval. JSON reads ok = containers read back over HTTP as JSON matching what the device wrote.
