# Aegis Swarm

Aegis Swarm is an edge-first drone orchestration simulation for disaster Search and Rescue.  
It connects an AI orchestrator, an MCP server bridge, and a 2D simulation so drone fleets can be discovered dynamically, assigned missions, monitored for battery limits, and re-routed when failures happen.

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
