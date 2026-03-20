# Drone Promax

`Drone Promax` is an edge-first autonomous drone swarm simulation for disaster search-and-rescue in low-connectivity environments.

This project demonstrates how an AI coordinator can control a fleet through MCP tools only, while handling battery limits, drone failures, and real-time mission coverage.

## Why This Matters (Hackathon Context)

In the first 72 hours after disasters, cloud connectivity can fail but rescue decisions still need to continue.

`drone promax` focuses on:
- resilient autonomous coordination
- decentralized recovery behavior
- practical mission visibility for command teams

## What the Judges Should Look For

- End-to-end MCP-driven orchestration (no direct hidden control path)
- Dynamic drone discovery and assignment
- Battery-aware planning with return-to-base logic
- Self-healing task reassignment when drones go offline
- Live visual command-center style monitoring

## Core Features

- Autonomous mission planning from high-level command input
- Runtime tool-based fleet discovery with `list_drones()`
- Path and scan execution via `move_to(...)` and `thermal_scan(...)`
- Safety checks with `get_battery_status(...)`
- Mission status monitoring with `get_mission_status()`
- Local (Ollama) and cloud (OpenRouter) LLM provider options

## System Architecture

- `agent/`: orchestrator, prompt policy, visual panel, offline MCP agent
- `server/`: FastMCP bridge and tool contracts
- `sim/`: deterministic grid simulation and pygame renderer
- `models/`: drone state model definitions
- `tests/`: mission and behavior validation

## Repository Layout

```text
agent/
  offline_ollama_mcp_agent.py
  orchestrator.py
  prompts.py
  visual_offline_panel.py
docs/
models/
outputs/
server/
  fastmcp_bridge.py
sim/
  environment.py
  pygame_renderer.py
models/
  drone_state.py
tests/
tools/
README.md
SPEC.md
requirements.txt
```

## Tech Stack

- Python 3.10+
- FastMCP-style tool bridge
- Pygame simulation renderer
- An installed 'mesa' dependency for the simulation
- LLM provider options:
  - OpenRouter (cloud)
  - Ollama : qwen3 8B (local/offline-friendly)

## Quick Start (Windows / PowerShell)

1. Install dependencies:

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


## Quick Start

Run the MCP bridge:

```powershell
python -m server.fastmcp_bridge
```

3. Start orchestrator:

```powershell
python -m agent.orchestrator
```

## Demo Commands (Judge-Friendly)

Run visual command panel (OpenRouter):

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider openrouter --rounds 0
```

Run visual command panel (Ollama fallback):

```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider ollama --rounds 0
```


## MCP Tool Contract

Required tools:
- `list_drones()`
- `move_to(drone_id, x, y)`
- `get_battery_status(drone_id)`
- `thermal_scan(drone_id)`

Additional mission visibility tool:
- `get_mission_status()`

Standard response shape:
- success: `{"ok": true, "data": ...}`
- error: `{"ok": false, "error": {"code": "...", "message": "...", "details": ...}}`

## Validation

Run tests:

```powershell
py -m pytest
```

Smoke-test MCP tool availability:

```powershell
python .\tools\mcp_smoke_test.py
```

## Impact Summary

`drone promax` is designed to show practical autonomous resilience for emergency response:
- keeps mission progress under degraded connectivity
- reallocates tasks when units fail
- protects uptime with battery-aware behavior
- provides transparent, monitorable command flow for responders

