## Codec runs

| run | host | format | size vs JSON | encode µs | decode µs |
|---|---:|---:|---:|---:|---:|
| 20261110-172407-codec-laptop | a4-band-am2076.ad.psu.edu | json | 1.0 | 1.6 | 1.28 |
| 20261110-172407-codec-laptop | a4-band-am2076.ad.psu.edu | cbor | 0.756 | 2.33 | 1.44 |
| 20261110-172407-codec-laptop | a4-band-am2076.ad.psu.edu | pb | 0.434 | 3.63 | 3.84 |

## End-to-end runs

| run | host | operation | format | n | wire B/exchange | vs JSON | RTT median ms | p95 | notify ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20261110-172429-e2e-laptop-local | a4-band-am2076.ad.psu.edu | create_cin | json | 300 | 1457.7 | 1.0 | 1.11 | 1.38 | 1.38 |
| 20261110-172429-e2e-laptop-local | a4-band-am2076.ad.psu.edu | create_cin | cbor | 300 | 1125.6 | 0.772 | 1.12 | 1.35 | 1.43 |
| 20261110-172429-e2e-laptop-local | a4-band-am2076.ad.psu.edu | create_cin | pb | 300 | 809.5 | 0.555 | 1.14 | 1.38 | 1.41 |
| 20261110-172429-e2e-laptop-local | a4-band-am2076.ad.psu.edu | retrieve_la | json | 300 | 689.5 | 1.0 | 1.09 | 1.38 |  |
| 20261110-172429-e2e-laptop-local | a4-band-am2076.ad.psu.edu | retrieve_la | cbor | 300 | 540.9 | 0.785 | 1.14 | 1.45 |  |
| 20261110-172429-e2e-laptop-local | a4-band-am2076.ad.psu.edu | retrieve_la | pb | 300 | 393.4 | 0.571 | 1.15 | 1.46 |  |
| 20261110-172441-e2e-laptop-local-plain | a4-band-am2076.ad.psu.edu | create_cin | json | 200 | 1203.0 | 1.0 | 1.1 | 1.56 | 1.4 |
| 20261110-172441-e2e-laptop-local-plain | a4-band-am2076.ad.psu.edu | create_cin | cbor | 200 | 903.8 | 0.751 | 1.18 | 1.59 | 1.55 |
| 20261110-172441-e2e-laptop-local-plain | a4-band-am2076.ad.psu.edu | create_cin | pb | 200 | 590.7 | 0.491 | 1.14 | 1.59 | 1.48 |
| 20261110-172441-e2e-laptop-local-plain | a4-band-am2076.ad.psu.edu | retrieve_la | json | 200 | 604.2 | 1.0 | 1.27 | 1.58 |  |
| 20261110-172441-e2e-laptop-local-plain | a4-band-am2076.ad.psu.edu | retrieve_la | cbor | 200 | 466.6 | 0.772 | 1.26 | 1.62 |  |
| 20261110-172441-e2e-laptop-local-plain | a4-band-am2076.ad.psu.edu | retrieve_la | pb | 200 | 320.1 | 0.53 | 1.26 | 1.61 |  |
