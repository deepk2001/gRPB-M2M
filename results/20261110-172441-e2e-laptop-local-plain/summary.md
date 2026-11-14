## End to end: laptop-local-plain (200 iterations, content='plain')

| operation | format | n | request B | response B | notification B | wire B/exchange | wire vs JSON | RTT median ms | p95 | p99 | notify median ms | errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| create_cin | json | 200 | 178.60 | 408.20 | 474.20 | 1203.00 | 1.00 | 1.10 | 1.56 | 1.70 | 1.40 | 0 |
| create_cin | cbor | 200 | 138.60 | 289.60 | 333.60 | 903.80 | 0.75 | 1.18 | 1.59 | 1.88 | 1.55 | 0 |
| create_cin | pb | 200 | 98.60 | 169.10 | 193.10 | 590.70 | 0.49 | 1.14 | 1.59 | 1.89 | 1.48 | 0 |
| retrieve_la | json | 200 | 101 | 408.20 |  | 604.20 | 1.00 | 1.27 | 1.58 | 1.72 |  | 0 |
| retrieve_la | cbor | 200 | 83 | 289.60 |  | 466.60 | 0.77 | 1.26 | 1.62 | 2.06 |  | 0 |
| retrieve_la | pb | 200 | 65 | 169.10 |  | 320.10 | 0.53 | 1.26 | 1.61 | 1.87 |  | 0 |

wire B/exchange = MQTT PUBLISH packets for request + response (+ notification), including topics; PUBACKs are the same size for every format and are left out.
