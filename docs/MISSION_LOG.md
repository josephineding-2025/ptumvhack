# Mission Log Template

## Demo Session Metadata
- Date:
- Operator:
- Grid Size:
- Initial Drone Count:
- Active MCP Tools:

## Chronological Log
| Time | Event | Details |
| :--- | :--- | :--- |
| HH:MM:SS | Startup | Agent booted and discovered drones via `list_drones()`. |
| HH:MM:SS | Reasoning | `<thinking>` emitted before first action. |
| HH:MM:SS | Tool Call | `move_to(drone_id, x, y)` |
| HH:MM:SS | Tool Call | `thermal_scan(drone_id)` |
| HH:MM:SS | Battery Check | `get_battery_status(drone_id)` led to recall/reassignment. |
| HH:MM:SS | Recovery | Drone offline detected and abandoned sector reassigned. |

## Final Metrics
- Total searched cells:
- Coverage ratio:
- Survivors detected:
- Drones recovered/reassigned:
- Mission completion status:
