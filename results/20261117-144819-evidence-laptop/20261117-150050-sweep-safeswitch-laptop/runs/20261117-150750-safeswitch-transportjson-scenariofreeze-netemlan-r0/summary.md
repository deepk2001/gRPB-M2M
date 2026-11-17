## safeswitch: transportjson-scenariofreeze-netemlan-r0

| transport | scenario | network | p50 ms | cmds in outage | fast fail | timed out | ctrl blocked s | fails fast after ms | recovery ms | STALE executions | max late s | ran but reported failed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| json | freeze | lan | 1.04 | 40 | 0 | 35 | 70.10 | never | 1017.40 | 45 | 15.94 | 45 |

STALE = a command executed more than the deadline after it was issued, i.e. after the controller had given up on it. ran but reported failed = the controller recorded an error, yet the actuator carried the command out. fails fast after = time from the failure until commands to the dead group fail immediately instead of waiting for the deadline (median over the group's actuators).
