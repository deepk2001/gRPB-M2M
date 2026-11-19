## Sweep: farmnet (pi4)

| set_format | set_nodes | set_netem | achieved_per_s | errors | device_link_B_per_reading | fleet_MB_per_day | rtt_p50_ms | rtt_p95_ms | interop_ok | cse_cpu_mean | error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| json | 10 | lan | 2.0 | 0 | 765.0 | 132.19 | 16.064 | 36.736 | 10 | 6.2 |  |
| json | 10 | wifi | 2.0 | 0 | 765.0 | 132.19 | 29.958 | 62.347 | 10 | 6.1 |  |
| json | 10 | 4g | 2.0 | 0 | 765.0 | 132.19 | 204.125 | 305.575 | 10 | 6.1 |  |
| json | 10 | constrained | 2.0 | 0 | 765.0 | 132.19 | 460.789 | 792.965 | 10 | 6.3 |  |
| json | 50 | lan | 10.0 | 0 | 766.6 | 662.35 | 24.566 | 71.652 | 10 | 30.4 |  |
| json | 50 | wifi | 10.0 | 0 | 766.6 | 662.35 | 59.937 | 264.194 | 10 | 33.4 |  |
| json | 50 | 4g | 10.0 | 0 | 766.6 | 662.34 | 240.788 | 504.029 | 10 | 36.3 |  |
| json | 50 | constrained | 10.0 | 0 | 767.4 | 663.07 | 617.352 | 1391.458 | 10 | 41.1 |  |
| json | 200 | lan | 4.27 | 987 | 729.0 | 2519.28 | 9450.919 | 9947.64 | 0 | 108.3 |  |
| json | 200 | wifi | 0.0 | 1200 | 650.3 | 2247.43 |  |  | 0 | 107.0 |  |
| json | 200 | 4g | 0.0 | 1199 | 581.9 | 2010.92 |  |  | 0 | 105.8 |  |
| json | 200 | constrained | 0.0 | 1200 | 525.3 | 1815.56 |  |  | 0 | 105.0 |  |
| cbor | 10 | lan | 2.0 | 0 | 588.6 | 101.71 | 68.481 | 131.838 | 10 | 20.4 |  |
| cbor | 10 | wifi | 2.0 | 0 | 588.6 | 101.71 | 83.088 | 189.935 | 10 | 20.6 |  |
| cbor | 10 | 4g | 2.0 | 0 | 588.6 | 101.71 | 249.66 | 444.144 | 10 | 20.0 |  |
| cbor | 10 | constrained | 2.0 | 0 | 588.6 | 101.71 | 479.534 | 772.551 | 10 | 20.5 |  |
| cbor | 50 | lan | 9.23 | 0 | 566.2 | 489.21 | 5377.515 | 6547.648 | 10 | 103.7 |  |
| cbor | 50 | wifi | 8.57 | 0 | 567.3 | 490.12 | 6140.099 | 6614.448 | 10 | 103.4 |  |
| cbor | 50 | 4g | 8.12 | 0 | 570.7 | 493.09 | 6453.258 | 6844.532 | 10 | 102.9 |  |
| cbor | 50 | constrained | 7.72 | 0 | 572.1 | 494.34 | 6770.57 | 7216.141 | 10 | 103.0 |  |
| cbor | 200 | lan | 0.0 | 1200 | 346.0 | 1195.87 |  |  | 0 | 104.4 |  |
| cbor | 200 | wifi |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=eee70219943e within 10.0s (is the CSE running with 'cbor' enabled?) |
| cbor | 200 | 4g |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=779ee18cb153 within 10.0s (is the CSE running with 'cbor' enabled?) |
| cbor | 200 | constrained |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=24b52cb0963b within 10.0s (is the CSE running with 'cbor' enabled?) |
| pb | 10 | lan |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=ccb828c93d18 within 10.0s (is the CSE running with 'pb' enabled?) |
| pb | 10 | wifi | 2.0 | 0 | 430.6 | 74.41 | 117.562 | 196.451 | 10 | 27.8 |  |
| pb | 10 | 4g | 2.0 | 0 | 432.8 | 74.79 | 266.514 | 525.931 | 10 | 27.7 |  |
| pb | 10 | constrained | 2.0 | 0 | 428.4 | 74.02 | 523.251 | 876.732 | 10 | 28.1 |  |
| pb | 50 | lan | 6.45 | 0 | 423.2 | 365.65 | 8093.796 | 8435.211 | 10 | 103.6 |  |
| pb | 50 | wifi | 6.23 | 0 | 423.6 | 365.99 | 8313.619 | 8626.46 | 10 | 103.8 |  |
| pb | 50 | 4g | 6.02 | 0 | 424.8 | 366.99 | 8587.158 | 8970.38 | 10 | 103.4 |  |
| pb | 50 | constrained | 5.9 | 0 | 426.9 | 368.82 | 8645.157 | 9095.082 | 10 | 103.1 |  |
| pb | 200 | lan | 0.0 | 1200 | 246.7 | 852.43 |  |  | 0 | 103.9 |  |
| pb | 200 | wifi |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=77d822d4a22d within 10.0s (is the CSE running with 'pb' enabled?) |
| pb | 200 | 4g |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=67d0ca69d9c9 within 10.0s (is the CSE running with 'pb' enabled?) |
| pb | 200 | constrained |  |  |  |  |  |  |  |  | grpb.onem2m.client.Onem2mError: no response to rqi=6d3660957d4d within 10.0s (is the CSE running with 'pb' enabled?) |
