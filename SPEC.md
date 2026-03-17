# Aegis Swarm - Case Study 3 Execution Specification

## 1. Context and Goal

This project implements Case Study 3: "First Responder of the Future - Decentralised Swarm Intelligence."

- Disaster context: first 72 hours after typhoon/earthquake when cellular and internet infrastructure may fail.
- Core challenge: centralized cloud rescue orchestration becomes unavailable.
- Required response: edge-first autonomous command agent coordinating a simulated drone fleet using MCP.
- SDG alignment from case brief:
- SDG 9 (Targets 9.1, 9.5).
- SDG 3 (Target 3.d).

## 2. Mandatory Constraints from Case Brief

1. Simulation only.
- Use 2D grid or simple Python simulation.
- No physical drone hardware integration.
2. MCP-only control path.
- All agent-to-drone actions must go through MCP tools.
- Hard-coded movement logic inside the LLM planning layer is not allowed.
3. Reasoning before action.
- Emit concise `<thinking>` before each MCP tool call.
- Reasoning must mention battery, distance, and/or coverage tradeoff.
4. Runtime drone discovery.
- Agent must discover active drones dynamically.
- No fixed drone IDs in planning policy.

## 3. Required MVP Capabilities

1. Autonomous mission planning from high-level command to sequenced tool calls.
2. MCP server exposing required tools.
3. Strategic resource management:
- battery-aware recall before failure,
- workload reallocation.
4. Self-healing behavior:
- detect offline drone state,
- reassign abandoned sectors.

## 4. Required MCP Tool Contract

The system must expose these exact tool names:

1. `list_drones() -> list[dict]`
2. `move_to(drone_id: str, x: int, y: int) -> str`
3. `get_battery_status(drone_id: str) -> dict`
4. `thermal_scan(drone_id: str) -> str`

Compatibility aliases are optional, but these names are non-negotiable.

## 5. Target System Architecture

1. `agent/orchestrator.py`
- command decomposition,
- mission queue generation,
- `<thinking>` emission,
- MCP tool invocation sequence.
2. `agent/prompts.py`
- role/system prompt,
- response policy constraints,
- tool-call reasoning format.
3. `server/fastmcp_bridge.py`
- MCP server startup,
- tool registration,
- argument validation and errors.
4. `sim/environment.py`
- grid state,
- drone state transitions,
- battery and scan logic,
- mission metrics.
5. `sim/pygame_renderer.py`
- visual demo support,
- optional offline trigger for self-healing demo.
6. `docs/MISSION_LOG.md`
- evidence timeline and compliance checklist.

## 6. Team Ownership and Detailed Responsibilities

### Member 1 - MCP / Protocol Lead

Primary ownership:
- `server/fastmcp_bridge.py`

What to do:
1. Implement and expose required MCP tools exactly:
- `list_drones`,
- `move_to`,
- `get_battery_status`,
- `thermal_scan`.
2. Ensure tool schemas are stable and documented:
- input types,
- return payload structure,
- error payload format.
3. Add safe error handling:
- unknown drone ID,
- out-of-bounds coordinate,
- offline drone operation.
4. Ensure server runtime can start locally with one command.
5. Define tool-level logging format for mission evidence.

Deliverables:
1. Working local MCP server process.
2. Tool contract reference section in README or server docstring.
3. Basic smoke test checklist for tool availability.

Definition of done:
1. Required tool names appear in MCP discovery list.
2. All required tools return deterministic JSON/string shapes.
3. Error cases are non-crashing and human-readable.

Dependencies:
- Must align return payload shape with Member 2 simulation fields.
- Must publish final tool interface for Member 3 integration.

### Member 2 - Simulation Lead

Primary ownership:
- `sim/environment.py`
- `sim/pygame_renderer.py`
- `models/drone_state.py`

What to do:
1. Implement deterministic grid simulation:
- default 20x20,
- base at `(0, 0)`,
- seeded survivor positions.
2. Create 3-5 initial drones with required fields:
- `id`, `location`, `battery`, `status`.
3. Implement battery policy:
- movement cost = Manhattan distance,
- fixed scan cost,
- recall threshold `<= 15%`.
4. Implement state transitions:
- `IDLE`, `SEARCHING`, `CHARGING`, `OFFLINE`.
5. Implement mission metrics function:
- searched cells,
- coverage ratio,
- survivors found,
- active/offline drones.
6. Implement one deterministic offline event trigger for demo.

Deliverables:
1. Stable simulation API callable by server bridge.
2. Deterministic scenario seed for repeatable demo runs.
3. Renderer optional path for visual demonstration.

Definition of done:
1. Same sequence of actions produces same outcomes.
2. Battery and coverage metrics update correctly per action.
3. Offline drone behavior blocks actions and is recoverable by reassignment.

Dependencies:
- Must match tool expectations in Member 1 bridge.
- Must provide metric keys required by Member 3 planning logic.

### Member 3 - Agent / Orchestrator Lead

Primary ownership:
- `agent/orchestrator.py`
- `agent/prompts.py`

What to do:
1. Implement discovery-first planning flow:
- call `list_drones` before any assignment.
2. Implement mission decomposition:
- high-level command -> sector tasks -> tool calls.
3. Enforce `<thinking>` before every tool call.
4. Implement battery-aware decision policy:
- if battery at/below threshold, issue recall and reassign task.
5. Implement self-healing policy:
- when drone unavailable/offline, requeue abandoned sector.
6. Keep logic tool-driven:
- no direct simulation mutation from orchestrator.

Deliverables:
1. Runnable mission loop producing ordered reasoning + actions.
2. Prompt policy that enforces MCP-only behavior.
3. Structured runtime mission log entries for docs/demo.

Definition of done:
1. Every MCP call has a preceding `<thinking>`.
2. First action sequence starts with runtime fleet discovery.
3. Low battery and offline events cause reassignment, not mission halt.

Dependencies:
- Requires stable tool interfaces from Member 1.
- Requires deterministic simulation semantics from Member 2.

### Member 4 - Ops / QA / Documentation Lead

Primary ownership:
- `docs/MISSION_LOG.md`
- `docs/PHASE0_PLAN.md`
- `presentation/PITCH_DECK_OUTLINE.md`
- top-level runbook updates (README-related coordination)

What to do:
1. Define demo runbook:
- startup order,
- commands to run,
- expected output checkpoints.
2. Capture mission evidence:
- timestamps,
- `<thinking>` snippets,
- tool call sequence,
- recovery events.
3. Validate acceptance checklist against live run.
4. Build judging narrative:
- problem -> architecture -> demo -> SDG impact.
5. Coordinate final dry runs and defect triage list.

Deliverables:
1. Completed mission log with one successful self-healing run.
2. Demo checklist with pass/fail markers.
3. Presentation outline connected to actual run evidence.

Definition of done:
1. Independent teammate can replay demo from docs only.
2. Mission log proves all mandatory constraints were met.
3. Deck claims are backed by run artifacts.

Dependencies:
- Requires mission outputs from Members 1-3.

## 7. Detailed Implementation Plan (Instruction-Only)

### Phase 0 - Contract Lock (Day 0)

1. Confirm mandatory constraints and required tool names in this `SPEC.md`.
2. Freeze API payload shapes for:
- drone object,
- battery response,
- mission status response.
3. Confirm owner per file and PR boundary.

Exit criteria:
1. Team agrees on tool signatures and response formats.
2. No ambiguous ownership remains.

### Phase 1 - Vertical Slice (Day 1)

1. Member 2 prepares seeded simulation with 3-5 drones.
2. Member 1 exposes MCP endpoints mapped to simulation functions.
3. Member 3 runs one command producing:
- discovery,
- one move,
- one scan,
- logged `<thinking>`.
4. Member 4 captures this as first mission-log artifact.

Exit criteria:
1. One end-to-end happy-path run works locally.

### Phase 2 - Resource Management (Day 2)

1. Member 2 verifies battery drain and recall threshold behavior.
2. Member 1 validates error-safe responses for low-battery and invalid calls.
3. Member 3 adds recall decision and reassignment logic.
4. Member 4 updates checklist for battery compliance evidence.

Exit criteria:
1. At least one drone recall is demonstrated and logged.

### Phase 3 - Self-Healing (Day 3)

1. Member 2 adds deterministic offline trigger.
2. Member 1 ensures bridge surfaces offline state clearly.
3. Member 3 reassigns abandoned sectors automatically.
4. Member 4 captures before/after timeline for failure recovery.

Exit criteria:
1. Mission continues after one drone goes offline.

### Phase 4 - Hardening and Demo Packaging (Day 4)

1. Member 1: tool smoke tests and startup reliability.
2. Member 2: deterministic scenario stability checks.
3. Member 3: reasoning/log consistency checks.
4. Member 4: final mission log + presentation + runbook.

Exit criteria:
1. Full acceptance checklist passes in one clean run.

## 8. Integration Contracts Between Members

1. Simulation -> MCP bridge contract:
- canonical drone ID key: `id`,
- location format: `[x, y]`,
- status values: `IDLE|SEARCHING|CHARGING|OFFLINE`.
2. MCP bridge -> Agent contract:
- keep required tool names exactly as in Section 4.
- return machine-parseable output for decision logic.
3. Agent -> Documentation contract:
- each tool call entry includes time, tool name, args summary, result summary.
- `<thinking>` captured immediately before each tool action.

## 9. Acceptance Checklist (Team-Level)

1. Discovery-first behavior confirmed (`list_drones` before assignment).
2. MCP-only execution path confirmed.
3. `<thinking>` appears before every tool call.
4. Battery recall policy demonstrated (`<= 15%`).
5. Offline drone reassignment demonstrated.
6. Final mission metrics include coverage and survivors found.

## 10. References (From Case Study Resource Section)

Protocol:
1. https://modelcontextprotocol.io/introduction
2. https://github.com/modelcontextprotocol/python-sdk
3. https://github.com/jlowin/fastmcp
4. https://github.com/langchain-ai/langchain-mcp-adapters

Simulation:
1. https://mesa.readthedocs.io/

Agent Frameworks:
1. https://docs.crewai.com/
2. https://microsoft.github.io/autogen/stable/reference/python/autogen_ext.tools.mcp.html

Vercel AI SDK:
1. https://ai-sdk.dev/docs/introduction
