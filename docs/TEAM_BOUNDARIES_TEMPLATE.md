# Team Boundaries Template

Use this directly with the Case Study 3 scaffold.

## Shared (All Members)
- Project structure and repository conventions
- Common tooling, CI, and coding standards
- Mandatory MCP-only control policy and reasoning-log format

## Member 1 (MCP / Protocol)
- Own `server/fastmcp_bridge.py`
- Implement MCP tool registration and runtime serving
- Guarantee support for `list_drones`, `move_to`, `get_battery_status`, `thermal_scan`

## Member 2 (Simulation)
- Own `sim/environment.py` and `sim/pygame_renderer.py`
- Implement drone movement, battery drain, survivor scan, and offline events
- Provide deterministic test scenario with at least 3-5 drones

## Member 3 (Agent)
- Own `agent/orchestrator.py` and `agent/prompts.py`
- Implement discovery-first planning and MCP tool-call sequencing
- Ensure `<thinking>` appears before each tool action

## Member 4 (Ops / Demo / Documentation)
- Own `docs/MISSION_LOG.md` and presentation artifacts
- Capture timeline evidence of reasoning, tool calls, and self-healing
- Validate SDG linkage and judging narrative

## Notes
- Keep interfaces between member-owned modules explicit.
- Avoid overlapping ownership to reduce merge conflicts.
