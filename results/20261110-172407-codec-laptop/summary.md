## Codec: size and CPU on real ACME primitives

| format | bytes, all primitives | size vs JSON | encode µs (median) | decode µs (median) |
|---|---:|---:|---:|---:|
| json | 2501 | 1.00 | 1.60 | 1.28 |
| cbor | 1891 | 0.76 | 2.33 | 1.44 |
| pb | 1085 | 0.43 | 3.63 | 3.84 |

### Bytes per primitive

| primitive | json | cbor | pb | pb/json |
|---|---:|---:|---:|---:|
| AE_CREATE | 172 | 120 | 81 | 47% |
| AE_CREATED | 346 | 262 | 143 | 41% |
| CNT_CREATED | 301 | 228 | 112 | 37% |
| SUB_CREATE | 148 | 103 | 65 | 44% |
| CIN_CREATE | 136 | 100 | 69 | 51% |
| CIN_CREATED | 333 | 259 | 145 | 44% |
| NOTIFY | 396 | 307 | 172 | 43% |
| RETRIEVE_LA | 79 | 60 | 47 | 59% |
| CNT_UPDATED | 320 | 242 | 122 | 38% |
| NOT_FOUND | 165 | 132 | 86 | 52% |
| DELETED | 105 | 78 | 43 | 41% |
