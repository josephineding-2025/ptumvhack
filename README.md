# Aegis Swarm

Aegis Swarm is an edge-first drone orchestration simulation for disaster Search and Rescue.  
It connects an AI orchestrator, an MCP server bridge, and a 2D simulation so drone fleets can be discovered dynamically, assigned missions, monitored for battery limits, and re-routed when failures happen.

This repository is scaffolded for "Case Study 3: First Responder of the Future - Decentralised Swarm Intelligence" with mandatory MCP-only agent control.

## Setup
1. Install Python 3.10+.
2. From the repository root, run:
```powershell
.\tools\setup.ps1
```
3. Create your environment file:
```powershell
Copy-Item .env.example .env
```
4. Fill required values in `.env`:
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` (default: `https://openrouter.ai/api/v1`)
- `OPENROUTER_MODEL` (default: `arcee-ai/trinity-large-preview:free`)

If your OpenRouter account has no credits, use the default free model above. You still need a valid `OPENROUTER_API_KEY`.

## Required MCP Tool Names
- `list_drones()`
- `move_to(drone_id, x, y)`
- `get_battery_status(drone_id)`
- `thermal_scan(drone_id)`

## MCP Tool Return Format (JSON)
All MCP tools return JSON objects with a consistent envelope:
- Success: `{"ok": true, "data": ...}`
- Error: `{"ok": false, "error": {"code": "...", "message": "...", "details": ...}}`

## Quick Start (Scaffold Demo)
1. Run orchestrator startup mission:
```powershell
python -m agent.orchestrator
```
2. Run MCP server bridge:
```powershell
python -m server.fastmcp_bridge
```
3. Optional simulation renderer:
```powershell
python -c "from sim.environment import SimulationEnvironment; from sim.pygame_renderer import PygameRenderer; PygameRenderer(SimulationEnvironment()).run()"
```

## Offline Agent (Ollama + MCP)
Use this path when cloud models are unavailable.

1. Install dependencies once:
```powershell
.\tools\setup.ps1
```
2. Start Ollama service:
```powershell
ollama serve
```
3. Ensure model is present:
```powershell
ollama pull qwen3:8b
```
4. Verify MCP bridge and tools (no LLM involved):
```powershell
python .\tools\mcp_smoke_test.py
```
5. Run the offline agent (it will spawn MCP bridge via stdio):
```powershell
python -m agent.offline_ollama_mcp_agent --command "Start SAR mission and maximize coverage"
```

The offline runner uses:
- `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434/v1`)
- `OLLAMA_MODEL` (default `qwen3:8b`)
- `MCP_COMMAND` + `MCP_ARGS` (default `<current interpreter> -m server.fastmcp_bridge`)

### MCP stdio troubleshooting (Windows)
If you see JSON-RPC parse errors like `Invalid JSON ... input_value='\\n'`, remove stale override values in `.env`:
```powershell
MCP_COMMAND=
MCP_ARGS=-m server.fastmcp_bridge
```
This forces the agent to launch MCP with the same Python interpreter already running your program.

## Orchestrator Backends
- Default strict MCP transport path:
```powershell
python -m agent.orchestrator --tool-backend mcp --iterations 50
```
- Local debug path with renderer:
```powershell
python -m agent.orchestrator --tool-backend local --render --iterations 50
```

## Visual AI Command Center
Run your agent with a simulation panel and a live thinking box:
```powershell
python -m agent.visual_offline_panel --provider ollama --command "Start SAR mission, maximize coverage, and report survivors." --rounds 20
```

Use local model explicitly:
```powershell
python -m agent.visual_offline_panel --provider ollama --model qwen3:8b --command "Start SAR mission, maximize coverage, and report survivors."
```

Use cloud model explicitly with a free OpenRouter model:
```powershell
python -m agent.visual_offline_panel --provider openrouter --model arcee-ai/trinity-large-preview:free --command "Start SAR mission, maximize coverage, and report survivors."
```

Automatic mode (cloud when reachable, local otherwise):
```powershell
python -m agent.visual_offline_panel --provider auto --command "Start SAR mission and keep patrolling while scanning."
```
