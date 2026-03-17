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
- `OPENROUTER_MODEL` (default: `openai/gpt-4o`)

## Required MCP Tool Names
- `list_drones()`
- `move_to(drone_id, x, y)`
- `get_battery_status(drone_id)`
- `thermal_scan(drone_id)`

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
