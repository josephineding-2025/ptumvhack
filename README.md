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
Fill out necessary keys like `OPENROUTER_API_KEY` or `OLLAMA_BASE_URL` inside your `.env` file. 🔐

### 🕹️ 2. Run the Command Center
You can instantly start the visual search-and-rescue mission panel relying on automatic provider selection:
```powershell
.\.venv\Scripts\python.exe -m agent.visual_offline_panel --provider auto --command "Start SAR mission and keep patrolling while scanning." --rounds 0
```

### 🏎️ 3. Alternative Advanced Execution
If you wish to independently start the MCP tool backend and orchestrator manually:

```powershell
# In terminal 1
python -m server.fastmcp_bridge

# In terminal 2
python -m agent.orchestrator --tool-backend mcp --iterations 50
```

## 📂 Project Structure
```text
.
├── agent/      ─ Central orchestration, LLM prompts, and visual control loops 🧠
├── docs/       ─ Requirements, case study specifications (SPEC.md), and logs 📜
├── models/     ─ Drone state representations and internal data models 🏗️
├── server/     ─ FastMCP bridge exposing required drone tools 🔌
├── sim/        ─ Grid simulation, drone behavior transitions, and Pygame renderer 🎮
├── tests/      ─ Software behavior and mission-level test schemas ✅
├── tools/      ─ Setup scripts and system smoke tests 🛠️
└── README.md   ─ Primary documentation 📘
```

---

<div align="center">
  <b>Built by doctech with ❤️ (and a bit of AI)</b>
</div>
