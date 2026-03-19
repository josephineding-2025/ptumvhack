import argparse
import asyncio
import os
import re
import socket
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient, load_mcp_tools
from langchain_openai import ChatOpenAI

from agent.prompts import MISSION_START_PROMPT, SYSTEM_PROMPT, user_command_prompt
from sim.environment import SimulationEnvironment
from sim.pygame_renderer import PygameRenderer


@dataclass
class VisualConfig:
    ollama_base_url: str
    ollama_model: str
    openrouter_base_url: str
    openrouter_model: str
    openrouter_api_key: str
    ollama_timeout_sec: float
    mcp_command: str
    mcp_args: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "VisualConfig":
        default_python = sys.executable or "python"
        configured_command = os.getenv("MCP_COMMAND", "").strip() or default_python
        if configured_command.lower() == "python":
            configured_command = default_python
        return cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            ollama_timeout_sec=float(os.getenv("OLLAMA_TIMEOUT_SEC", "45")),
            mcp_command=configured_command,
            mcp_args=tuple(os.getenv("MCP_ARGS", "-m server.fastmcp_bridge").split()),
        )


@dataclass
class VisualState:
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=240))
    full_logs: list[str] = field(default_factory=list)
    pending_commands: deque[str] = field(default_factory=deque)
    pending_offline_ids: deque[str] = field(default_factory=deque)
    lock: threading.RLock = field(default_factory=threading.RLock)
    done: bool = False
    mission_complete: bool = False
    exported_log_path: str | None = None

    def push(self, message: str) -> None:
        with self.lock:
            self.logs.append(message)
            self.full_logs.append(message)

    def push_command(self, command: str) -> None:
        text = command.strip()
        if not text:
            return
        with self.lock:
            self.pending_commands.append(text)
            self.logs.append(f"[user] {text}")

    def get_logs(self) -> list[str]:
        with self.lock:
            return list(self.logs)

    def get_full_logs(self) -> list[str]:
        with self.lock:
            return list(self.full_logs)

    def pop_command(self) -> str | None:
        with self.lock:
            if not self.pending_commands:
                return None
            return self.pending_commands.popleft()

    def push_offline(self, drone_id: str) -> None:
        with self.lock:
            self.pending_offline_ids.append(drone_id)
            self.logs.append(f"[user] fail {drone_id}")

    def pop_offline(self) -> str | None:
        with self.lock:
            if not self.pending_offline_ids:
                return None
            return self.pending_offline_ids.popleft()

    def mark_done(self) -> None:
        with self.lock:
            self.done = True

    def set_mission_complete(self, exported_log_path: str | None = None) -> None:
        with self.lock:
            self.mission_complete = True
            self.exported_log_path = exported_log_path

    def get_completion_state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "done": self.done,
                "mission_complete": self.mission_complete,
                "exported_log_path": self.exported_log_path,
            }


@dataclass
class VisualSnapshot:
    lock: threading.RLock = field(default_factory=threading.RLock)
    drones: list[dict[str, Any]] = field(default_factory=list)
    mission_status: dict[str, Any] = field(
        default_factory=lambda: {
            "grid_size": [20, 20],
            "coverage_ratio": 0.0,
            "searched_cells": 0,
            "survivors_found": 0,
            "total_survivors": 0,
            "all_survivors_found": False,
            "active_drones": 0,
            "total_drones": 0,
        }
    )

    def update(self, drones: list[dict[str, Any]], mission_status: dict[str, Any]) -> None:
        with self.lock:
            self.drones = drones
            self.mission_status = mission_status

    def get_drones(self) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.drones)

    def get_status(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.mission_status)


def _extract_agent_text(result: Any) -> str:
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            content = getattr(last, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_chunks = []
                for chunk in content:
                    if isinstance(chunk, dict) and "text" in chunk:
                        text_chunks.append(str(chunk["text"]))
                if text_chunks:
                    return " ".join(text_chunks)
            if isinstance(last, dict):
                dict_content = last.get("content")
                if isinstance(dict_content, str):
                    return dict_content
    return str(result)


def _build_mission_log_markdown(
    command: str,
    mission_status: dict[str, Any],
    drones: list[dict[str, Any]],
    logs: list[str],
) -> str:
    grid_size = mission_status.get("grid_size", [20, 20])
    offline_ids = [str(item) for item in mission_status.get("offline_drone_ids", [])]
    total_battery = sum(int(drone.get("battery", 0)) for drone in drones)
    average_battery = (total_battery / len(drones)) if drones else 0.0
    coverage_pct = float(mission_status.get("coverage_ratio", 0.0)) * 100.0
    survivors_found = int(mission_status.get("survivors_found", 0))

    lines = [
        "# Mission Log",
        "",
        "## Demo Session Metadata",
        f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Objective: {command or 'N/A'}",
        f"- Grid Size: {grid_size[0]}x{grid_size[1]}" if isinstance(grid_size, list) and len(grid_size) == 2 else "- Grid Size: N/A",
        f"- Active Drones at End: {mission_status.get('active_drones', 0)}",
        f"- Total Drones: {mission_status.get('total_drones', 0)}",
        "",
        "## Search Log",
    ]
    for entry in logs:
        lines.append(f"- {entry}")

    lines.extend(
        [
            "",
            "## Mission Post-Mortem Table",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| Total Grid Covered (%) | {coverage_pct:.1f} |",
            f"| Survivors Rescued (Count) | {survivors_found} |",
            f"| Average Battery Remaining (%) | {average_battery:.1f} |",
            f"| Drones Lost in Action (Count) | {len(offline_ids)} |",
        ]
    )
    return "\n".join(lines) + "\n"


def _export_mission_log(
    command: str,
    mission_status: dict[str, Any],
    drones: list[dict[str, Any]],
    logs: list[str],
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.getcwd(), "outputs", "mission_logs")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"mission_log_{timestamp}.md")
    content = _build_mission_log_markdown(command, mission_status, drones, logs)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def _host_reachable(url: str, timeout_sec: float = 2.0) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except Exception:
        return False


def _normalize_tool_response(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict) and "text" in first:
            import json

            return json.loads(first["text"])
    raise RuntimeError(f"Unexpected MCP response format: {type(raw).__name__}")


def _is_objective_met(command: str, mission_status: dict[str, Any]) -> bool:
    objective = command.strip().lower()
    if not objective:
        return False
    coverage = float(mission_status.get("coverage_ratio", 0.0))
    all_survivors_found = bool(mission_status.get("all_survivors_found", False))

    percentage_match = re.search(r"(\d{1,3})\s*%", objective)
    if percentage_match:
        target = max(0, min(100, int(percentage_match.group(1)))) / 100.0
        if coverage >= target:
            return True

    if "entire grid" in objective or "full grid" in objective or "100%" in objective:
        return coverage >= 1.0
    if "all survivors" in objective or "every survivor" in objective:
        return all_survivors_found
    if "survivor" in objective and "report" in objective:
        return int(mission_status.get("survivors_found", 0)) > 0
    return False


async def _refresh_snapshot(tool_map: dict[str, Any], snapshot: VisualSnapshot) -> None:
    fleet_response = _normalize_tool_response(await tool_map["list_drones"].ainvoke({}))
    mission_response = _normalize_tool_response(await tool_map["get_mission_status"].ainvoke({}))
    live_drones = fleet_response.get("data", {}).get("drones", []) if fleet_response.get("ok") else []
    mission_status = mission_response.get("data", {}) if mission_response.get("ok") else {}
    offline_ids = {str(did) for did in mission_status.get("offline_drone_ids", [])}

    previous = {str(item.get("id", "")): dict(item) for item in snapshot.get_drones() if item.get("id")}
    merged: dict[str, dict[str, Any]] = {}
    for drone in live_drones:
        drone_id = str(drone.get("id", ""))
        if not drone_id:
            continue
        merged[drone_id] = dict(drone)
    for drone_id in offline_ids:
        prior = dict(previous.get(drone_id, {"id": drone_id, "location": [0, 0], "battery": 0}))
        prior["status"] = "OFFLINE"
        merged[drone_id] = prior

    # Preserve deterministic ordering by drone id for stable rendering/assignment.
    drones = [merged[key] for key in sorted(merged.keys())]
    snapshot.update(drones=drones, mission_status=mission_status)


async def run_visual_agent(
    command: str,
    ui: VisualState,
    snapshot: VisualSnapshot,
    rounds: int = 12,
    plan_timeout: float | None = None,
    provider: str = "auto",
    model_override: str | None = None,
) -> None:
    cfg = VisualConfig.from_env()
    timeout_sec = plan_timeout if plan_timeout is not None else cfg.ollama_timeout_sec
    ui.push("Agent booting (cloud/local auto + MCP tools).")

    selected_provider = provider
    if provider == "auto":
        openrouter_ready = bool(cfg.openrouter_api_key) and _host_reachable(cfg.openrouter_base_url)
        selected_provider = "openrouter" if openrouter_ready else "ollama"
        ui.push(f"[agent] provider auto -> {selected_provider}")

    if selected_provider == "openrouter":
        if not cfg.openrouter_api_key:
            ui.push("[error] OPENROUTER_API_KEY is missing in .env")
            ui.mark_done()
            return
        selected_model = model_override or cfg.openrouter_model
        ui.push(f"Agent provider: openrouter ({selected_model})")
        llm = ChatOpenAI(
            model=selected_model,
            base_url=cfg.openrouter_base_url,
            api_key=cfg.openrouter_api_key,
            temperature=0,
            timeout=timeout_sec,
        )
    else:
        selected_model = model_override or cfg.ollama_model
        ui.push(f"Agent provider: ollama ({selected_model})")
        llm = ChatOpenAI(
            model=selected_model,
            base_url=cfg.ollama_base_url,
            api_key="ollama",
            temperature=0,
            timeout=timeout_sec,
        )

    client = MultiServerMCPClient(
        {
            "aegis_swarm": {
                "transport": "stdio",
                "command": cfg.mcp_command,
                "args": list(cfg.mcp_args),
            }
        }
    )

    try:
        async with client.session("aegis_swarm") as session:
            loaded_tools = await load_mcp_tools(session, server_name="aegis_swarm")
            tool_map = {loaded_tool.name: loaded_tool for loaded_tool in loaded_tools}
            await _refresh_snapshot(tool_map, snapshot)
            assigned_waypoints: dict[str, tuple[int, int]] = {}
            round_stats: dict[str, int] = {"move_calls": 0, "status_calls": 0}

            def _location_for(drone_id: str) -> tuple[int, int] | None:
                for item in snapshot.get_drones():
                    if str(item.get("id", "")) != drone_id:
                        continue
                    loc = item.get("location", [0, 0])
                    if isinstance(loc, list) and len(loc) == 2:
                        return int(loc[0]), int(loc[1])
                return None

            @tool
            async def list_drones() -> dict:
                """List currently active drones."""
                ui.push(
                    "<thinking>I need live fleet discovery first so sector planning adapts to active drones and failures.</thinking>"
                )
                result = _normalize_tool_response(await tool_map["list_drones"].ainvoke({}))
                await _refresh_snapshot(tool_map, snapshot)
                count = len(result.get("data", {}).get("drones", [])) if result.get("ok") else 0
                ui.push(f"[tool] list_drones -> {count} active")
                return result

            @tool
            async def move_to(drone_id: str, x: int, y: int) -> dict:
                """Move a drone to target coordinates on the grid."""
                target = (int(x), int(y))
                current_loc = _location_for(drone_id)
                existing = assigned_waypoints.get(drone_id)
                if existing is not None and current_loc is not None and current_loc != existing:
                    status = _normalize_tool_response(
                        await tool_map["get_battery_status"].ainvoke({"drone_id": drone_id})
                    )
                    await _refresh_snapshot(tool_map, snapshot)
                    return {
                        "ok": True,
                        "data": {
                            "message": (
                                f"{drone_id} already en route to waypoint [{existing[0]}, {existing[1]}]. "
                                "Central command waits until arrival."
                            ),
                            "battery_status": status.get("data", {}),
                        },
                    }

                ui.push(
                    f"<thinking>{drone_id} is being assigned strategic waypoint [{target[0]},{target[1]}], while edge pathing handles local movement and collision avoidance.</thinking>"
                )
                result = _normalize_tool_response(
                    await tool_map["move_to"].ainvoke({"drone_id": drone_id, "x": target[0], "y": target[1]})
                )
                round_stats["move_calls"] += 1
                await _refresh_snapshot(tool_map, snapshot)
                if result.get("ok"):
                    battery = result.get("data", {}).get("battery_status", {}).get("battery", "?")
                    message = str(result.get("data", {}).get("message", "")).lower()
                    loc = result.get("data", {}).get("battery_status", {}).get("location", [0, 0])
                    accepted = ("accepted waypoint" in message) or ("already executing waypoint" in message)
                    if accepted and isinstance(loc, list) and len(loc) == 2 and (int(loc[0]), int(loc[1])) != target:
                        assigned_waypoints[drone_id] = target
                    else:
                        assigned_waypoints.pop(drone_id, None)
                    ui.push(f"[tool] move_to({drone_id},{target[0]},{target[1]}) -> {battery}%")
                else:
                    error = result.get("error", {}).get("message", "unknown error")
                    ui.push(f"[tool:error] move_to({drone_id},{target[0]},{target[1]}) -> {error}")
                return result

            @tool
            async def thermal_scan(drone_id: str) -> dict:
                """Run thermal scan at current drone location."""
                ui.push(
                    f"<thinking>{drone_id} reached a useful sector, so I am validating survivor presence with thermal sensing.</thinking>"
                )
                result = _normalize_tool_response(await tool_map["thermal_scan"].ainvoke({"drone_id": drone_id}))
                await _refresh_snapshot(tool_map, snapshot)
                if result.get("ok") and result.get("data", {}).get("detected"):
                    loc = result.get("data", {}).get("battery_status", {}).get("location", [0, 0])
                    if isinstance(loc, list) and len(loc) == 2:
                        ui.push(
                            f"<thinking>Survivor detected at exact coordinates [{int(loc[0])}, {int(loc[1])}]. Continuing mission search.</thinking>"
                        )
                message = result.get("data", {}).get("message", "") if result.get("ok") else result.get("error", {}).get(
                    "message", "unknown error"
                )
                label = "[tool]" if result.get("ok") else "[tool:error]"
                ui.push(f"{label} thermal_scan({drone_id}) -> {message}")
                return result

            @tool
            async def get_battery_status(drone_id: str) -> dict:
                """Get battery/state information for one drone."""
                ui.push(
                    f"<thinking>I need {drone_id}'s battery state before assigning a longer sector or recalling it.</thinking>"
                )
                result = _normalize_tool_response(
                    await tool_map["get_battery_status"].ainvoke({"drone_id": drone_id})
                )
                await _refresh_snapshot(tool_map, snapshot)
                if result.get("ok"):
                    battery = result.get("data", {}).get("battery", "?")
                    ui.push(f"[tool] get_battery_status({drone_id}) -> {battery}%")
                else:
                    error = result.get("error", {}).get("message", "unknown error")
                    ui.push(f"[tool:error] get_battery_status({drone_id}) -> {error}")
                return result

            @tool
            async def get_mission_status() -> dict:
                """Get mission-wide coverage and fleet metrics."""
                ui.push(
                    "<thinking>I need mission coverage and fleet status before reallocating sectors or continuing the sweep.</thinking>"
                )
                result = _normalize_tool_response(await tool_map["get_mission_status"].ainvoke({}))
                round_stats["status_calls"] += 1
                await _refresh_snapshot(tool_map, snapshot)
                if result.get("ok"):
                    coverage = float(result.get("data", {}).get("coverage_ratio", 0.0)) * 100
                    ui.push(f"[tool] get_mission_status -> coverage {coverage:.1f}%")
                else:
                    error = result.get("error", {}).get("message", "unknown error")
                    ui.push(f"[tool:error] get_mission_status -> {error}")
                return result

            round_idx = 1
            active_command = command.strip()
            if not active_command:
                ui.push("[agent] waiting for user command in chatbox (example: search north east area).")
            no_assignment_backoff_sec = 2.0
            next_dispatch_time = 0.0
            last_assigned_target: dict[str, tuple[int, int]] = {}

            async def fallback_assign_waypoints() -> int:
                # Anti-stall fallback: assign strategic waypoints if LLM round produced no movement.
                fleet_response = _normalize_tool_response(await tool_map["list_drones"].ainvoke({}))
                mission_response = _normalize_tool_response(await tool_map["get_mission_status"].ainvoke({}))
                await _refresh_snapshot(tool_map, snapshot)
                drones = fleet_response.get("data", {}).get("drones", [])
                mission = mission_response.get("data", {})
                grid = mission.get("grid_size", [20, 20])
                width, height = int(grid[0]), int(grid[1])
                searched = {
                    (int(p[0]), int(p[1]))
                    for p in mission.get("searched_positions", [])
                    if isinstance(p, (list, tuple)) and len(p) == 2
                }
                if not drones:
                    return 0

                objective = active_command.lower()
                base = (0, 0)
                ordered_ids = sorted(
                    str(d.get("id", ""))
                    for d in drones
                    if d.get("id") and str(d.get("status", "")) != "OFFLINE"
                )
                if not ordered_ids:
                    return 0

                def objective_allows(x: int, y: int) -> bool:
                    if "east" in objective and x < width // 2:
                        return False
                    if "west" in objective and x >= width // 2:
                        return False
                    if "north" in objective and y >= height // 2:
                        return False
                    if "south" in objective and y < height // 2:
                        return False
                    return True

                def build_wavefront_anchors(total: int, frontier_radius: int) -> list[tuple[int, int]]:
                    radius = max(0, min(frontier_radius, (width - 1) + (height - 1)))
                    x_min = max(0, radius - (height - 1))
                    x_max = min(width - 1, radius)
                    while x_min > x_max and radius > 0:
                        radius -= 1
                        x_min = max(0, radius - (height - 1))
                        x_max = min(width - 1, radius)
                    if total <= 0:
                        return []
                    available_x = list(range(x_min, x_max + 1))
                    if not available_x:
                        return [(0, 0)] * total
                    chosen_x: list[int] = []
                    used_x: set[int] = set()
                    for idx in range(total):
                        raw_x = x_min if total == 1 else x_min + round((x_max - x_min) * idx / (total - 1))
                        best_x = min(
                            available_x,
                            key=lambda value: (value in used_x, abs(value - raw_x), value),
                        )
                        chosen_x.append(best_x)
                        used_x.add(best_x)
                    return [(x, radius - x) for x in chosen_x]

                searched_frontier = max((x + y for x, y in searched), default=0)
                wavefront_radius = min((width - 1) + (height - 1), max(4, searched_frontier + 2))
                wavefront_anchors = build_wavefront_anchors(len(ordered_ids), wavefront_radius)
                anchor_by_drone = {
                    drone_id: wavefront_anchors[idx]
                    for idx, drone_id in enumerate(ordered_ids)
                }

                assignment_lines: list[str] = []
                used_targets: set[tuple[int, int]] = set()
                for drone_id in ordered_ids:
                    drone = next((item for item in drones if str(item.get("id", "")) == drone_id), None)
                    if drone is None:
                        continue
                    if not drone_id:
                        continue
                    loc = drone.get("location", [0, 0])
                    if not isinstance(loc, list) or len(loc) != 2:
                        continue
                    current = (int(loc[0]), int(loc[1]))
                    status = str(drone.get("status", ""))
                    if status == "OFFLINE":
                        continue
                    existing = assigned_waypoints.get(drone_id)
                    if existing is not None and current != existing:
                        continue
                    battery = int(drone.get("battery", 0))
                    preferred_anchor = anchor_by_drone.get(drone_id, base)

                    candidates: list[tuple[int, int]] = []
                    min_assignment_distance = 3
                    for x in range(width):
                        for y in range(height):
                            point = (x, y)
                            if point in searched or point in used_targets or point == current:
                                continue
                            if not objective_allows(x, y):
                                continue
                            # Keep a strict return reserve.
                            travel = abs(current[0] - x) + abs(current[1] - y)
                            ret = abs(x - base[0]) + abs(y - base[1])
                            # Keep extra reserve margin to avoid oscillation at battery edge.
                            if battery <= (travel + ret + 2):
                                continue
                            # Avoid trivial short hops that create assignment/wait loops.
                            if travel < min_assignment_distance:
                                continue
                            # Avoid repeatedly hugging base unless no other option.
                            if abs(x - base[0]) + abs(y - base[1]) <= 2:
                                continue
                            candidates.append(point)
                    if not candidates:
                        # Fallback to any unsearched safe point.
                        for x in range(width):
                            for y in range(height):
                                point = (x, y)
                                if point in searched or point in used_targets or point == current:
                                    continue
                                travel = abs(current[0] - x) + abs(current[1] - y)
                                ret = abs(x - base[0]) + abs(y - base[1])
                                if battery <= (travel + ret + 2):
                                    continue
                                candidates.append(point)
                    if not candidates:
                        # No safe exploration target: recall once for recharge if not already at base.
                        if current != base:
                            move_result = _normalize_tool_response(
                                await tool_map["move_to"].ainvoke({"drone_id": drone_id, "x": base[0], "y": base[1]})
                            )
                            message = str(move_result.get("data", {}).get("message", "")).lower()
                            accepted = move_result.get("ok") and ("accepted waypoint" in message or "already executing waypoint" in message)
                            if accepted:
                                assigned_waypoints[drone_id] = base
                                assignment_lines.append(f"{drone_id}->[0,0]")
                        continue
                    # Keep the swarm on a balanced diagonal wavefront so coverage expands as one search front.
                    previous_target = last_assigned_target.get(drone_id)
                    candidates.sort(key=lambda p: (
                        abs(preferred_anchor[0] - p[0]) + abs(preferred_anchor[1] - p[1]),
                        -(abs(p[0] - base[0]) + abs(p[1] - base[1])),
                        abs(current[0] - p[0]) + abs(current[1] - p[1]),
                        p[0],
                        p[1],
                    ))
                    target = candidates[0]
                    if previous_target is not None and target == previous_target and len(candidates) > 1:
                        target = candidates[1]
                    move_result = _normalize_tool_response(
                        await tool_map["move_to"].ainvoke({"drone_id": drone_id, "x": target[0], "y": target[1]})
                    )
                    message = str(move_result.get("data", {}).get("message", "")).lower()
                    accepted = move_result.get("ok") and ("accepted waypoint" in message or "already executing waypoint" in message)
                    if accepted:
                        assigned_waypoints[drone_id] = target
                        last_assigned_target[drone_id] = target
                        used_targets.add(target)
                        assignment_lines.append(f"{drone_id}->[{target[0]},{target[1]}]")
                await _refresh_snapshot(tool_map, snapshot)
                if assignment_lines:
                    ui.push("<thinking>Issuing a balanced diagonal wavefront so the swarm expands coverage as one coordinated search shape.</thinking>")
                    ui.push(f"<thinking>Assigned waypoints: {', '.join(assignment_lines)}</thinking>")
                return len(assignment_lines)

            async def wait_until_waypoints_reached(max_wait_sec: float = 120.0) -> None:
                if not assigned_waypoints:
                    return
                ui.push("<thinking>Waiting for edge drones to autonomously reach assigned waypoints before the next planning round.</thinking>")
                start = asyncio.get_running_loop().time()
                last_snapshot: dict[str, tuple[int, int]] = {}
                stagnant_cycles = 0
                while assigned_waypoints:
                    await _refresh_snapshot(tool_map, snapshot)
                    fleet_now = snapshot.get_drones()
                    current_snapshot: dict[str, tuple[int, int]] = {}
                    fleet_ids = {str(d.get("id", "")) for d in fleet_now}
                    for drone_id in list(assigned_waypoints.keys()):
                        if drone_id not in fleet_ids:
                            assigned_waypoints.pop(drone_id, None)
                    for drone in fleet_now:
                        drone_id = str(drone.get("id", ""))
                        if drone_id not in assigned_waypoints:
                            continue
                        status = str(drone.get("status", ""))
                        loc = drone.get("location", [0, 0])
                        if status == "OFFLINE":
                            assigned_waypoints.pop(drone_id, None)
                            continue
                        if isinstance(loc, list) and len(loc) == 2:
                            current = (int(loc[0]), int(loc[1]))
                            current_snapshot[drone_id] = current
                            if current == (0, 0) and status in {"CHARGING", "IDLE"}:
                                assigned_waypoints.pop(drone_id, None)
                                continue
                            if current == assigned_waypoints[drone_id]:
                                assigned_waypoints.pop(drone_id, None)
                    if not assigned_waypoints:
                        break
                    stagnant_drones: list[str] = []
                    for drone_id, pos in current_snapshot.items():
                        if last_snapshot.get(drone_id) == pos:
                            stagnant_drones.append(drone_id)
                    if stagnant_drones and len(stagnant_drones) == len(current_snapshot):
                        stagnant_cycles += 1
                    else:
                        stagnant_cycles = 0
                    last_snapshot = current_snapshot
                    if stagnant_cycles >= 12:
                        # Fail-safe: clear only stuck drones and continue wave progression.
                        for drone_id in list(current_snapshot.keys()):
                            assigned_waypoints.pop(drone_id, None)
                        ui.push("[warn] autonomous waypoint progress stalled for current wave; clearing stuck waypoint waits and continuing.")
                        break
                    if asyncio.get_running_loop().time() - start >= max_wait_sec:
                        ui.push("[warn] waypoint wait timeout reached; continuing with next planning round.")
                        break
                    await asyncio.sleep(0.15)

            while True:
                if rounds > 0 and round_idx > rounds:
                    ui.push(f"[agent] Reached configured round limit ({rounds}).")
                    break
                queued_command = ui.pop_command()
                if queued_command:
                    active_command = queued_command
                    ui.push(f"[agent] objective accepted: {active_command}")
                queued_offline = ui.pop_offline()
                while queued_offline:
                    offline_tool = tool_map.get("set_drone_offline")
                    if offline_tool is None:
                        ui.push("[warn] set_drone_offline MCP tool unavailable; restart bridge after pulling latest code.")
                        break
                    offline_result = _normalize_tool_response(await offline_tool.ainvoke({"drone_id": queued_offline}))
                    status_msg = offline_result.get("data", {}).get("message", "")
                    ui.push(f"[tool] set_drone_offline({queued_offline}) -> {status_msg or 'ok'}")
                    await _refresh_snapshot(tool_map, snapshot)
                    queued_offline = ui.pop_offline()

                # Drop completed waypoint tracking for drones that arrived.
                fleet_now = snapshot.get_drones()
                for drone in fleet_now:
                    drone_id = str(drone.get("id", ""))
                    loc = drone.get("location", [0, 0])
                    if drone_id not in assigned_waypoints:
                        continue
                    if isinstance(loc, list) and len(loc) == 2:
                        if (int(loc[0]), int(loc[1])) == assigned_waypoints[drone_id]:
                            assigned_waypoints.pop(drone_id, None)

                if not active_command:
                    await asyncio.sleep(0.2)
                    continue

                mission_status = snapshot.get_status()
                coverage = float(mission_status.get("coverage_ratio", 0.0))
                all_survivors_found = bool(mission_status.get("all_survivors_found", False))
                full_grid_scanned = coverage >= 1.0
                objective_met = _is_objective_met(active_command, mission_status)
                if all_survivors_found or full_grid_scanned or objective_met:
                    ui.push(
                        "<thinking>Mission completion condition met. Edge drones are autonomously returning to base under Mesa completion policy.</thinking>"
                    )
                    ui.push("[agent] MISSION COMPLETE")
                    await _refresh_snapshot(tool_map, snapshot)
                    exported_path = _export_mission_log(
                        active_command,
                        snapshot.get_status(),
                        snapshot.get_drones(),
                        ui.get_full_logs(),
                    )
                    ui.push(f"[agent] Mission log saved: {exported_path}")
                    ui.set_mission_complete(exported_path)
                    break

                # Central wave control: assign waypoints, wait for completion, then reassign next wave.
                if not assigned_waypoints:
                    now = asyncio.get_running_loop().time()
                    if now >= next_dispatch_time:
                        assigned_count = await fallback_assign_waypoints()
                        if assigned_count > 0:
                            ui.push("<thinking>All drones are idle at assigned points. Sending next central waypoint wave now.</thinking>")
                            next_dispatch_time = now + 0.5
                        else:
                            ui.push("<thinking>No safe new waypoints available. Holding until recharge/state change before next dispatch attempt.</thinking>")
                            next_dispatch_time = now + no_assignment_backoff_sec
                await wait_until_waypoints_reached(max_wait_sec=45.0)
                await _refresh_snapshot(tool_map, snapshot)
                await asyncio.sleep(0.2)
                round_idx += 1
    except Exception as exc:
        ui.push(f"[error] {type(exc).__name__}: {exc}")
    finally:
        ui.mark_done()


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run cloud/local agent with live simulation panel and thinking box."
    )
    parser.add_argument(
        "--command",
        default="",
        help="Initial mission command (leave empty to wait for chatbox command).",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=30,
        help="Grid cell size for renderer.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=0,
        help="How many agent planning rounds to run (0 = run continuously).",
    )
    parser.add_argument(
        "--plan-timeout",
        type=float,
        default=float(os.getenv("OLLAMA_TIMEOUT_SEC", "45")),
        help="Seconds to wait for each planning step before skipping it.",
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "ollama", "openrouter"),
        default="auto",
        help="Model backend for planning (auto prefers cloud when reachable).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override for selected provider.",
    )
    args = parser.parse_args()

    ui = VisualState()
    snapshot = VisualSnapshot()
    renderer_env = SimulationEnvironment()

    worker = threading.Thread(
        target=lambda: asyncio.run(
            run_visual_agent(
                args.command,
                ui,
                snapshot,
                rounds=args.rounds,
                plan_timeout=args.plan_timeout,
                provider=args.provider,
                model_override=args.model,
            )
        ),
        daemon=True,
    )
    worker.start()

    def status_provider() -> dict[str, Any]:
        return snapshot.get_status()

    def fleet_provider() -> list[dict[str, Any]]:
        return snapshot.get_drones()

    def submit_command(text: str) -> None:
        ui.push_command(text)

    def submit_offline(drone_id: str) -> None:
        ui.push_offline(drone_id)

    renderer = PygameRenderer(
        renderer_env,
        cell_size=args.cell_size,
        log_provider=ui.get_full_logs,
        status_provider=status_provider,
        fleet_provider=fleet_provider,
        command_submitter=submit_command,
        offline_submitter=submit_offline,
        completion_provider=ui.get_completion_state,
        state_lock=snapshot.lock,
    )
    renderer.run()


if __name__ == "__main__":
    main()
