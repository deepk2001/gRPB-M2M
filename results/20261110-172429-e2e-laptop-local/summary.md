## End to end: laptop-local (300 iterations, content='reading')

| operation | format | n | request B | response B | notification B | wire B/exchange | wire vs JSON | RTT median ms | p95 | p99 | notify median ms | errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| create_cin | json | 300 | 262.70 | 493.50 | 559.50 | 1457.70 | 1.00 | 1.11 | 1.38 | 1.63 | 1.38 | 0 |
| create_cin | cbor | 300 | 211.70 | 363.90 | 407.90 | 1125.60 | 0.77 | 1.12 | 1.35 | 1.53 | 1.43 | 0 |
| create_cin | pb | 300 | 170.70 | 242.40 | 266.40 | 809.50 | 0.56 | 1.14 | 1.38 | 1.55 | 1.41 | 0 |
| retrieve_la | json | 300 | 101 | 493.50 |  | 689.50 | 1.00 | 1.09 | 1.38 | 1.46 |  | 0 |
| retrieve_la | cbor | 300 | 83 | 363.90 |  | 540.90 | 0.79 | 1.14 | 1.45 | 1.60 |  | 0 |
| retrieve_la | pb | 300 | 65 | 242.40 |  | 393.40 | 0.57 | 1.15 | 1.46 | 1.60 |  | 0 |

wire B/exchange = MQTT PUBLISH packets for request + response (+ notification), including topics; PUBACKs are the same size for every format and are left out.
