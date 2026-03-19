# Aegis Swarm

Aegis Swarm is an edge-first drone swarm simulation for disaster search and rescue. It combines a central AI coordinator, an MCP tool bridge, and a 2D grid environment where drones search for survivors, manage battery constraints, recover from failures, and keep coverage progressing under degraded connectivity.

This repository was built around the disaster-response swarm intelligence case study, with MCP-only control as a core constraint.

## Highlights

- Dynamic fleet discovery through MCP tools
- Battery-aware waypoint assignment and return-to-base behavior
- Edge-side autonomous pathing and collision handling
- Self-healing reassignment when a drone goes offline
- Visual command-center panel for live mission monitoring
- Local or cloud-backed LLM control paths

## Architecture

The project is split into four main parts:

- `agent/`: central orchestration, prompts, and visual control loop
- `server/`: FastMCP bridge exposing the required drone tools
- `sim/`: grid simulation, drone behavior, charging, movement, and renderer
- `tests/`: behavior and mission-level checks

Core MCP tools exposed by the bridge:

- `list_drones()`
- `move_to(drone_id, x, y)`
- `get_battery_status(drone_id)`
- `thermal_scan(drone_id)`
- `get_mission_status()`

All MCP tools return a consistent JSON envelope:

- Success: `{"ok": true, "data": ...}`
- Error: `{"ok": false, "error": {"code": "...", "message": "...", "details": ...}}`

## Repository Layout

```text
agent/
  orchestrator.py
  prompts.py
  visual_offline_panel.py
server/
  fastmcp_bridge.py
sim/
  environment.py
  pygame_renderer.py
tests/
tools/
requirements.txt
README.md
```

## Requirements

- Python 3.10+
- PowerShell on Windows for the setup script
- An installed `mesa` dependency for the simulation
- Optional:
  - Ollama for local models
  - OpenRouter API key for cloud inference

## Setup

1. Install Python 3.10 or newer.
2. From the repository root, run:

```powershell
.\tools\setup.ps1
```

3. Create your local environment file:

```powershell
Copy-Item .env.example .env
```

4. Fill in the values you need in `.env`.

Common variables:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` default: `https://openrouter.ai/api/v1`
- `OPENROUTER_MODEL` default: `arcee-ai/trinity-large-preview:free`
- `OLLAMA_BASE_URL` default: `http://127.0.0.1:11434/v1`
- `OLLAMA_MODEL` default: `qwen3:8b`
- `MCP_COMMAND`
- `MCP_ARGS`

If you use OpenRouter's free model, you still need a valid API key.

## Quick Start

Run the MCP bridge:

```powershell
python -m server.fastmcp_bridge
```

Run the orchestrator:

```powershell
python -m agent.orchestrator
```

Run the simulation renderer directly:

```powershell
python -c "from sim.environment import SimulationEnvironment; from sim.pygame_renderer import PygameRenderer; PygameRenderer(SimulationEnvironment()).run()"
```

## Visual Command Center

Primary run command with OpenRouter:

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider openrouter --rounds 0
```

Backup run command with Ollama:

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider ollama --rounds 0
```

OpenRouter with an explicit model and mission command:

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider openrouter --model arcee-ai/trinity-large-preview:free --command "Start SAR mission, maximize coverage, and report survivors." --rounds 0
```

Ollama with an explicit local model and mission command:

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider ollama --model qwen3:8b --command "Start SAR mission, maximize coverage, and report survivors." --rounds 0
```

Automatic provider selection:

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider auto --command "Start SAR mission and keep patrolling while scanning." --rounds 0
```

## Offline Ollama Workflow

Use this path when you want fully local planning.

1. Start Ollama:

```powershell
ollama serve
```

2. Pull the model if needed:

```powershell
ollama pull qwen3:8b
```

3. Smoke-test the MCP bridge:

```powershell
python .\tools\mcp_smoke_test.py
```

4. Run the offline MCP-driven agent:

```powershell
python -m agent.offline_ollama_mcp_agent --command "Start SAR mission and maximize coverage"
```

## Orchestrator Modes

Strict MCP backend:

```powershell
python -m agent.orchestrator --tool-backend mcp --iterations 50
```

Local debug backend with renderer:

```powershell
python -m agent.orchestrator --tool-backend local --render --iterations 50
```

## Windows MCP Troubleshooting

If you hit JSON-RPC parse issues such as invalid newline input on Windows, clear stale `.env` overrides and keep the MCP launch command simple:

```powershell
MCP_COMMAND=
MCP_ARGS=-m server.fastmcp_bridge
```

That makes the agent reuse the current Python interpreter for the MCP bridge.

## Testing

Run the test suite with:

```powershell
py -m pytest
```

If tests fail during import with `ModuleNotFoundError: No module named 'mesa'`, install project dependencies first.

## Current Behavior

The simulation currently includes:

- launch gating so drones recharge at base before redeployment
- return-reserve battery checks before waypoint assignment
- central swarm shaping using a coordinated wavefront search pattern
- automatic recall and continued mission progress after failures

## Notes

- This repository may contain local experimental changes while development is in progress.
- The visual panel is intended for demos, debugging, and case-study presentation flow.
- If you plan to publish this publicly, add a license file and screenshots/GIFs for stronger GitHub presentation.
