## safeswitch: transportgrpc-scenariocrash-netemlan-r0

| transport | scenario | network | p50 ms | cmds in outage | fast fail | timed out | ctrl blocked s | fails fast after ms | recovery ms | STALE executions | max late s | ran but reported failed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grpc | crash | lan | 2.06 | 60 | 60 | 0 | 0.00 | 250.93 | 3427.84 | 0 | 0 | 0 |

STALE = a command executed more than the deadline after it was issued, i.e. after the controller had given up on it. ran but reported failed = the controller recorded an error, yet the actuator carried the command out. fails fast after = time from the failure until commands to the dead group fail immediately instead of waiting for the deadline (median over the group's actuators).
