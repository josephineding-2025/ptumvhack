# Aegis Swarm — Technical Specification

## 1. Project Overview

**Aegis Swarm** is an autonomous, decentralized drone orchestration system designed for post-disaster Search and Rescue (SAR) missions. It operates entirely at the "Edge," solving the critical issue of communication blackouts (e.g., collapsed 4G/5G infrastructure) during the first 72 hours of a natural disaster.

The system utilizes the **Model Context Protocol (MCP)** to standardize communication between an AI Orchestrator (the "Brain") and a simulated fleet of drones (the "Swarm"). Through Chain-of-Thought (CoT) reasoning, the AI dynamically assigns search sectors, monitors battery life, and instantly re-routes active drones if a team member fails, creating a truly "self-healing" network.

---

## 2. Target Users & Problem

### Target Users
- Disaster Management Agencies (e.g., NADMA Malaysia)
- First Responders and Fire & Rescue Departments
- Humanitarian Aid Organizations (Red Cross/Red Crescent)

### Problem
In the aftermath of typhoons, earthquakes, or severe floods in the ASEAN region, terrestrial communication infrastructure is often destroyed. Traditional cloud-based AI and centralized drone control systems become useless without the internet. Rescue teams are forced to rely on manual, uncoordinated efforts, losing precious time during the "golden 72 hours" when survivor rescue rates are highest.

There is a critical need for an offline, edge-deployable swarm system that can coordinate itself without a central human pilot or cloud server.

---

## 3. System Architecture

### Overview
Because this is a hackathon simulation, the architecture consists of three local components communicating via MCP. The AI Agent runs as the orchestrator, the MCP Server acts as the hardware bridge, and a Python-based UI visualizes the simulated physical world.

```text
┌──────────────────────────────────────────────┐
│           Agentic AI Orchestrator            │
│  - LangChain / AutoGen                       │
│  - Chain-of-Thought (CoT) Engine             │
│  - Mission Planner & Resource Manager        │
└────────────────────┬─────────────────────────┘
                     │ Model Context Protocol (MCP)
┌────────────────────▼─────────────────────────┐
│              FastMCP Server                  │
│  - Tool Registry (`list_drones`)             │
│  - Hardware Abstraction (`move_drone`)       │
│  - Sensor Abstraction (`scan_thermal`)       │
└────────────────────┬─────────────────────────┘
                     │ Internal State Updates
┌────────────────────▼─────────────────────────┐
│          2D Simulation Environment           │
│  - Grid-based Map (Mesa / PyGame)            │
│  - Drone Physics (Battery decay, Speed)      │
│  - Survivor/Obstacle Placement               │
│  - Live Dashboard / Heatmap                  │
└──────────────────────────────────────────────┘

```

## 4. Feature Specification

### 4.1 Real-Time Tool & Drone Discovery
**Purpose:** Ensure the AI does not rely on hard-coded drone IDs, simulating a plug-and-play mesh network.
* **Flow:** When the system boots, the AI queries the MCP server: *"What tools are available?"* -> The MCP server returns the active drone registry.
* **Dynamic:** If "Drone_4" is added to the simulation mid-mission, the AI discovers it on the next polling cycle and incorporates it into the search pattern.

### 4.2 Autonomous Mission Planning & CoT
**Purpose:** Decompose high-level human commands into strategic swarm movements.
* **Flow:** Human inputs: *"Search the Northern quadrant for survivors."*
* **CoT Execution:** Before moving, the Agent outputs its reasoning to the Mission Log:
  > *"I have 3 active drones. The Northern quadrant spans coordinates (0,10) to (10,10). Drone A is closest at (2,5) with 80% battery. Drone B is at (8,5) with 90% battery. I will assign Drone A to scan the NW sector and Drone B to scan the NE sector. Drone C will remain on standby."*

### 4.3 Strategic Resource Management (Battery)
**Purpose:** Prevent drones from crashing due to power loss.
* **Flow:** Every X simulated seconds, the Agent checks `get_battery_status()`.
* **Action:** If a drone drops below 15% battery, the Agent issues a `return_to_base()` command and immediately reassigns its unsearched sectors to the nearest available drone.

### 4.4 The "Self-Healing" Swarm (Disaster Recovery)
**Purpose:** The ultimate test of decentralization. Handle unexpected hardware failures.
* **Flow:** The user manually "kills" Drone A in the simulation UI.
* **Action:** The MCP server marks Drone A as `OFFLINE`. The AI Agent attempts to ping it, fails, explicitly logs the failure via CoT, and dynamically re-routes Drone B and C to cover Drone A's abandoned sector.

## 5. LLM & Agent Strategy

### Agent Framework: LangChain + FastMCP
We will use LangChain to orchestrate the agent loop, connecting it to our FastMCP server via `langchain-mcp-adapters`.

### System Prompt Design
> **System:**
> You are the Aegis Swarm Commander, an autonomous AI operating at the edge. 
> Your primary objective is to locate survivors in a disaster zone using a fleet of drones.
> 
> **CRITICAL RULES:**
> 1. DECENTRALIZATION: You must dynamically discover active drones. Do not assume drone IDs.
> 2. CHAIN OF THOUGHT: Before executing ANY tool, you must write a `<thinking>` block explaining your reasoning based on distance, battery life, and area coverage.
> 3. RESOURCE MANAGEMENT: Never let a drone's battery reach 0%. Recall them at 15%.
> 4. SELF-HEALING: If a drone goes offline, you must immediately re-assign its sector.
> 
> **User:**
> Initiate Search and Rescue protocol for the entire map grid (100x100).

### Simulated Edge Computing
While we may use an API (like OpenAI/OpenRouter) for the hackathon to ensure high-quality CoT reasoning, the architectural design explicitly represents an **Edge LLM** (e.g., Llama-3-8B running on a ruggedized local field laptop).

---

## 6. Simulation & Environment Model

### The World Grid
* **Dimensions:** 20x20 or 50x50 coordinate grid.
* **Entities:**
  * **Drones:** Have `(x, y)` position, `battery` (0-100), `status` (IDLE, SEARCHING, CHARGING, OFFLINE).
  * **Survivors:** Hidden `(x, y)` coordinates.
  * **Base Station:** `(0, 0)` - where drones spawn and charge.

### Physics & Logic
* Moving 1 grid square costs 1% battery.
* Scanning a grid square costs 2% battery.
* Thermal scanning reveals a survivor if the drone shares the exact `(x, y)` coordinate.

---

## 7. Tech Stack

| Component | Technology |
| :--- | :--- |
| **Agent Framework** | LangChain / LangGraph (Python) |
| **LLM Gateway** | OpenRouter (GPT-4o / Claude 3.5 Sonnet for strong CoT) |
| **Protocol Bridge** | FastMCP (Python SDK) |
| **Simulation Logic** | Mesa (Agent-based modeling) or standard Python Object-Oriented logic |
| **Visualization UI** | PyGame (2D Canvas) or Streamlit / Gradio (Web Dashboard) |
| **Logging** | Python `logging` to generate the official "Mission Log" |

---

## 8. MCP Protocol Contract

The FastMCP Server will expose the following standardized tools to the LLM:

### `get_active_fleet()`
* **Purpose:** Returns a list of currently online drones and their specs.
* **Response:** `[{"id": "drone_1", "battery": 95, "location": [0,0]}, ...]`

### `move_drone(drone_id: str, target_x: int, target_y: int)`
* **Purpose:** Commands a drone to move to a specific waypoint.
* **Response:** `"drone_1 moving to [10, 15]. Estimated arrival: 5 seconds."`

### `scan_sector(drone_id: str)`
* **Purpose:** Activates the simulated thermal camera at the current location.
* **Response:** `"Scan complete. 1 thermal signature detected!"` OR `"No signatures."`

### `get_mission_status()`
* **Purpose:** Returns the global state (total area searched, total survivors found).

## 9. Hackathon MVP Scope

### In Scope
- [x] Functional FastMCP server exposing 4+ tools.
- [x] LangChain Agent capable of complex CoT reasoning.
- [x] 2D visual simulation showing drones moving across a grid.
- [x] A successful "Self-Healing" demo (Agent recovers when a drone is manually deleted).
- [x] Real-time printing of the "Mission Log" in the terminal or UI.

### Out of Scope
- True peer-to-peer Wi-Fi Direct / LoRa mesh networking.
- 3D Unreal Engine / Unity simulations.
- Physical drone hardware (Pixhawk / DJI SDKs).

---

## 10. Team Ownership & Files

| Member | Role | Key Files |
| :--- | :--- | :--- |
| **Member 1** | System Architect (MCP) | `server/fastmcp_bridge.py`, `models/drone_state.py` |
| **Member 2** | Simulation Engineer | `sim/environment.py`, `sim/pygame_renderer.py` |
| **Member 3** | AI Orchestrator | `agent/orchestrator.py`, `agent/prompts.py` |
| **Member 4** | Strategy & Pitch | `docs/MISSION_LOG.md`, `presentation/pitch_deck.pdf` |

---

## 11. Implementation Roadmap

### Phase 0 — Scaffold & Environment
- [ ] Initialize Python virtual environment (`venv`).
- [ ] Install dependencies: `langchain`, `fastmcp`, `pygame`, `openai`.
- [ ] Member 2: Build a basic 20x20 grid array in Python.
- [ ] Member 2: Create a PyGame window that draws the grid and a few colored dots (drones).

### Phase 1 — The MCP Bridge (Member 1)
- [ ] Initialize `mcp = FastMCP("AegisSwarm")`.
- [ ] Write Python functions that update the backend grid state (move a dot, lower battery).
- [ ] Wrap these functions with `@mcp.tool()` decorators.
- [ ] Ensure the MCP server runs cleanly on `localhost`.

### Phase 2 — The Brain (Member 3)
- [ ] Setup LangChain with `ChatOpenAI` (via OpenRouter).
- [ ] Connect LangChain to the FastMCP server using `langchain-mcp-adapters`.
- [ ] Draft the System Prompt enforcing Chain-of-Thought.
- [ ] **Test:** Manually type "Move a drone to 5,5" in the terminal and watch the LLM trigger the MCP tool, which in turn moves the dot in the PyGame window.

### Phase 3 — Swarm Logic & Self-Healing (Members 1 & 3)
- [ ] Implement search logic: Prompt the AI to assign different quadrants to different drones to avoid overlap.
- [ ] Implement battery drain: Update the simulation so moving drains battery.
- [ ] Implement self-healing: Add a keyboard shortcut in PyGame to "kill" a drone. Verify the AI Agent notices it is missing on the next `get_active_fleet()` call and reassigns its work.

### Phase 4 — Polish & Documentation (Member 4)
- [ ] Capture the terminal output of the AI's reasoning and format it into a beautiful `MISSION_LOG.md`.
- [ ] Screen record the PyGame simulation running alongside the terminal showing the CoT reasoning.
- [ ] Finalize the Pitch Deck, aligning the project explicitly with SDG 9.1 (Resilient Infrastructure) and 3.d (Early Warning/Risk Reduction).
