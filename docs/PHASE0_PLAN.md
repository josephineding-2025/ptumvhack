# Phase 0 Plan (Case Study 3 Alignment)

## Objective
Lock the scaffold to Case Study 3 requirements so implementation starts with the correct MCP tool contract, mission constraints, and deliverable format.

## Completed
- Core repository scaffold created.
- `SPEC.md` updated for Case Study 3 mandatory constraints:
- simulation only
- MCP-only agent control
- reasoning log before tool calls
- runtime drone discovery (no hard-coded IDs)
- MCP bridge scaffold aligned to case-study tool names:
- `list_drones`
- `move_to`
- `get_battery_status`
- `thermal_scan`
- Mission log template aligned to required evidence.

## Remaining in Phase 0 (Shared)
1. Verify local environment creation and dependency installation.
2. Register MCP tools in `server/fastmcp_bridge.py` and run a local MCP server.
3. Seed simulation with 3-5 drones and baseline survivor coordinates.
4. Execute one end-to-end dry run with mission-log output.
5. Lock dependency versions after the first integration pass.

## Explicitly Out of Scope in This Step
- Full production agent loop and high-accuracy planning policy.
- Final UI polish and deck production work.
- Hardware deployment or physical drone integration.
