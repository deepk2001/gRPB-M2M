## farmnet: formatjson-nodes10-netemlan-r0

| format | nodes | network | readings/s | errors | device B/reading | notify B | fleet MB/day | RTT p50 ms | p95 | notify p95 ms | JSON reads ok | CSE CPU % | broker CPU % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| json | 10 | lan | 2.00 | 0 | 728.80 | 545.90 | 125.94 | 5.60 | 6.86 | 7.95 | 10 | 2.70 | 0.10 |

device B/reading = exact MQTT PUBLISH bytes of request + response on the device's own link (topics and properties included, PUBACKs excluded). fleet MB/day projects that over 24 h at this interval. JSON reads ok = containers read back over HTTP as JSON matching what the device wrote.
