# 🚁 Drone Promax 🛡️

## 🌍 Overview of the Project
Drone Promax is an edge-first drone swarm simulation designed for disaster search and rescue operations. It addresses the critical first 72 hours after events like typhoons or earthquakes when traditional communication infrastructure fails. By combining a central AI coordinator, a Model Context Protocol (MCP) tool bridge, and a 2D grid environment, Drone Promax continuously searches for survivors, discovers active drones, and pushes coverage progress in completely decentralized, disconnected scenarios. 🚨

## 💡 USP (Unique Selling Proposition)
**Fully Autonomous Edge-First Orchestration via MCP:** Drone Promax operates securely without hard-coded movement logic. It utilizes an advanced `<thinking>` and reasoning pattern enforced through the Model Context Protocol (MCP) before invoking any hardware tool. Coupled with native self-healing, the swarm automatically re-assigns workloads when unpredicted hardware failures occur, ensuring continuous operations without centralized cloud oversight. 📡

## ✨ Features
- 🚁 **Dynamic Fleet Discovery:** Runtime discovery and monitoring of active drones through native MCP tools.
- 🔋 **Battery-Aware Resource Management:** Calculates distance costs and autonomously recalls drones before they drop below the critical `15%` reserve threshold.
- 🛠️ **Self-Healing Architecture:** Instantly detects when a drone goes offline and re-queues abandoned search sectors to maintain mission progress.
- 🖥️ **Visual Command Center:** Real-time mission monitoring with a 2D local radar panel.
- 🧠 **Flexible Intelligence:** Supports switching between Local Edge Inference (Ollama) and Cloud Inference (OpenRouter) dynamically.

## 🛠️ Tech Stack
- 🐍 **Language:** Python 3.10+
- 🎮 **Simulation Engine:** `mesa` (Agent-based Modeling Framework), `pygame` (2D Visual Renderer)
- 🔗 **Protocol Layer:** Model Context Protocol (MCP), `fastmcp` (Tool Bridge)
- 🤖 **LLM Integrations:** `Ollama` (Offline / Local Models), `OpenRouter` (Cloud Multi-Model API)
- 🧪 **Testing:** `pytest`

## 🚀 Quick Start Guide

### 📋 Prerequisites
Make sure you have Python 3.10+ installed on your machine.
If you're on Windows, use PowerShell for these instructions.

### ⚙️ 1. Setup Environment
From the repository root, install the required dependencies:
```powershell
.\tools\setup.ps1
```

Create your local environment file:
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
