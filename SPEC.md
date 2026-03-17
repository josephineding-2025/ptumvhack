# Aegis Swarm - Case Study 3 Specification

## 1. Context

ASEAN countries are highly exposed to earthquakes and super typhoons. During the first 72 hours after impact, cell and internet infrastructure can fail, creating communication blackouts.

This project implements an edge-first rescue swarm where a central autonomous command agent coordinates simulated drones without cloud dependency.

- Track: Agentic AI (Decentralized Swarm Intelligence)
- SDG alignment:
- SDG 9 (Target 9.1 and 9.5): resilient infrastructure and innovation
- SDG 3 (Target 3.d): early warning and emergency response readiness

## 2. Problem Statement

Centralized cloud-dependent rescue coordination fails when infrastructure collapses. We need an Autonomous Command Agent that can:

1. Coordinate a fleet of drones at the edge.
2. Map disaster zones.
3. Detect survivors via on-device-like simulated sensing.
4. Manage resources and coverage through MCP-based tool calls.

## 3. Mandatory Constraints

1. Simulation-only implementation.
- No physical drone hardware is required.
- 2D grid or simple Python simulation environment is acceptable.
2. MCP-only control path.
- All agent-to-drone communication must happen through MCP tools.
- Hard-coded drone movement logic in the agent is prohibited.
3. Reasoning visibility before actions.
- Before each tool execution, the agent must log a concise `<thinking>` step that explains assignment decisions using battery, distance, and coverage.
4. Dynamic fleet discovery.
- The agent must discover active drones at runtime and must not rely on fixed drone IDs.

## 4. Technical Challenge Scope

1. Autonomous mission planning.
- Decompose high-level commands (for example, "scan south-east quadrant") into sequenced tool calls.
2. MCP tool integration.
- Expose standardized drone functions from an MCP server.
3. Strategic resource management.
- Track battery and recall drones before failure.
4. Self-healing behavior.
- Detect offline drones and reassign incomplete sectors.

## 5. Required MCP Tool Contract (Scaffold Target)

The scaffold must support, at minimum, these case-study tool names:

1. `list_drones()` for discovery.
2. `move_to(drone_id, x, y)` for navigation.
3. `get_battery_status(drone_id)` for battery-aware planning.
4. `thermal_scan(drone_id)` for survivor detection.

Compatibility helper names can exist, but the above names must remain supported.

## 6. Simulation Model Requirements

1. Grid environment with base station and searchable sectors.
2. 3-5 active drones in the mission scenario.
3. Drone state fields:
- `id`
- `location`
- `battery`
- `status` (`IDLE`, `SEARCHING`, `CHARGING`, `OFFLINE`)
4. Battery rules (default scaffold):
- Move cost by Manhattan distance.
- Scan cost per call.
- Recall threshold at or below 15%.

## 7. Deliverables

1. Orchestrator:
- A working AI agent that manages at least 3-5 simulated drones.
2. MCP server:
- MCP service exposing drone tools for agent use.
3. Mission log:
- Step-by-step reasoning and tool actions demonstrating successful SAR flow.

## 8. Recommended Stack

- Simulation: Mesa or Python-based custom grid.
- Agent framework: LangChain, AutoGen, or equivalent.
- Connector/Protocol: MCP Python SDK / FastMCP.

These are recommendations, not hard requirements.

## 9. Repository Scaffold Mapping

1. `agent/orchestrator.py`
- Agent loop, planning, reasoning log, and MCP tool execution.
2. `agent/prompts.py`
- System prompt enforcing MCP-only operation and reasoning visibility.
3. `server/fastmcp_bridge.py`
- MCP tool registration and server runtime.
4. `sim/environment.py`
- Simulation state, movement, scan logic, battery updates, and mission metrics.
5. `sim/pygame_renderer.py`
- Visualization and offline-drone trigger for self-healing demo.
6. `docs/MISSION_LOG.md`
- Demo evidence format and timeline.

## 10. Acceptance Criteria (MVP)

1. Agent performs discovery with `list_drones()` before assignments.
2. Agent outputs reasoning logs before tool calls.
3. Movement and scan actions are executed through MCP tools.
4. Low-battery drones are recalled and workload is reassigned.
5. When one drone goes offline, remaining drones continue and cover abandoned sectors.
6. Mission status reports coverage and survivor-detection progress.

