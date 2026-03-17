# Mission Log Template

## Demo Session Metadata
- Date:
- Operator:
- Grid Size:
- Initial Drone Count:
- Active MCP Tools:
- Recall Threshold:

## Chronological Log
| Time | Event | Details |
| :--- | :--- | :--- |
| HH:MM:SS | Startup | Agent booted and discovered drones via `list_drones()`. |
| HH:MM:SS | Reasoning | `<thinking>` emitted before first `move_to`. |
| HH:MM:SS | Tool Call | `move_to(drone_id, x, y)` |
| HH:MM:SS | Tool Call | `thermal_scan(drone_id)` |
| HH:MM:SS | Battery Check | `get_battery_status(drone_id)` triggered recall decision. |
| HH:MM:SS | Tool Call | `move_to(drone_id, 0, 0)` recall to base when battery <= 15%. |
| HH:MM:SS | Recovery | Drone offline detected and abandoned sector reassigned. |

## Final Metrics
- Total searched cells:
- Coverage ratio:
- Survivors detected:
- Drones recovered/reassigned:
- Mission completion status:

## Compliance Checklist
- [ ] Discovery happened before assignment (`list_drones`).
- [ ] Every tool call had preceding `<thinking>`.
- [ ] Required MCP tool names were used.
- [ ] At least one low-battery recall occurred.
- [ ] At least one offline/self-healing reassignment occurred.
