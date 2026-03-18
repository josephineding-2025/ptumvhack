import argparse
import asyncio
import os
import socket
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
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
    lock: threading.RLock = field(default_factory=threading.RLock)
    done: bool = False

    def push(self, message: str) -> None:
        with self.lock:
            self.logs.append(message)

    def get_logs(self) -> list[str]:
        with self.lock:
            return list(self.logs)

    def mark_done(self) -> None:
        with self.lock:
            self.done = True


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


async def _refresh_snapshot(tool_map: dict[str, Any], snapshot: VisualSnapshot) -> None:
    fleet_response = _normalize_tool_response(await tool_map["list_drones"].ainvoke({}))
    mission_response = _normalize_tool_response(await tool_map["get_mission_status"].ainvoke({}))
    drones = fleet_response.get("data", {}).get("drones", []) if fleet_response.get("ok") else []
    mission_status = mission_response.get("data", {}) if mission_response.get("ok") else {}
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
                ui.push(
                    f"<thinking>{drone_id} has enough battery and this move expands coverage, so I am sending it to [{int(x)},{int(y)}].</thinking>"
                )
                result = _normalize_tool_response(
                    await tool_map["move_to"].ainvoke({"drone_id": drone_id, "x": int(x), "y": int(y)})
                )
                await _refresh_snapshot(tool_map, snapshot)
                if result.get("ok"):
                    battery = result.get("data", {}).get("battery_status", {}).get("battery", "?")
                    ui.push(f"[tool] move_to({drone_id},{int(x)},{int(y)}) -> {battery}%")
                else:
                    error = result.get("error", {}).get("message", "unknown error")
                    ui.push(f"[tool:error] move_to({drone_id},{int(x)},{int(y)}) -> {error}")
                return result

            @tool
            async def thermal_scan(drone_id: str) -> dict:
                """Run thermal scan at current drone location."""
                ui.push(
                    f"<thinking>{drone_id} reached a useful sector, so I am validating survivor presence with thermal sensing.</thinking>"
                )
                result = _normalize_tool_response(await tool_map["thermal_scan"].ainvoke({"drone_id": drone_id}))
                await _refresh_snapshot(tool_map, snapshot)
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
                await _refresh_snapshot(tool_map, snapshot)
                if result.get("ok"):
                    coverage = float(result.get("data", {}).get("coverage_ratio", 0.0)) * 100
                    ui.push(f"[tool] get_mission_status -> coverage {coverage:.1f}%")
                else:
                    error = result.get("error", {}).get("message", "unknown error")
                    ui.push(f"[tool:error] get_mission_status -> {error}")
                return result

            agent = create_agent(
                model=llm,
                tools=[list_drones, move_to, get_battery_status, thermal_scan, get_mission_status],
                system_prompt=SYSTEM_PROMPT,
            )

            round_idx = 1
            while True:
                if rounds > 0 and round_idx > rounds:
                    ui.push(f"[agent] Reached configured round limit ({rounds}).")
                    break

                mission_status = snapshot.get_status()
                coverage = float(mission_status.get("coverage_ratio", 0.0))
                grid_size = mission_status.get("grid_size", [20, 20])
                if coverage >= 0.95:
                    objective_line = "Coverage target achieved; continue patrol sweeps and monitor battery while staying in-bounds."
                else:
                    objective_line = "Expand coverage with coordinated moves and thermal scans."

                rounds_label = str(rounds) if rounds > 0 else "continuous"
                mission_prompt = (
                    f"{MISSION_START_PROMPT}\n\n"
                    f"{user_command_prompt(command)}\n"
                    f"Round {round_idx}/{rounds_label}. Current coverage: {coverage*100:.1f}%.\n"
                    f"{objective_line}\n"
                    f"Grid bounds are x=0..{int(grid_size[0]) - 1}, y=0..{int(grid_size[1]) - 1}. Never propose coordinates outside bounds.\n"
                    "Execute at least one move_to and one thermal_scan if any active drone has battery above 15%.\n"
                    "Use short operational rationale in <thinking>; do not expose long hidden reasoning.\n"
                    "If a drone goes offline, explicitly reassign its sector across the remaining fleet.\n"
                    "Return a concise action summary."
                )
                ui.push(f"[agent] round {round_idx}: planning actions...")
                try:
                    result = await asyncio.wait_for(
                        agent.ainvoke({"messages": [("user", mission_prompt)]}),
                        timeout=timeout_sec,
                    )
                except asyncio.TimeoutError:
                    ui.push(f"[warn] planning timed out after {timeout_sec:.0f}s; moving to next round.")
                    round_idx += 1
                    continue
                summary = _extract_agent_text(result).strip().replace("\n", " ")
                if len(summary) > 220:
                    summary = summary[:220] + "..."
                ui.push(f"[agent] {summary}")
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
        default="Discover active drones, spread out for coverage, scan key sectors, and report findings.",
        help="Mission command for the local agent.",
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

    renderer = PygameRenderer(
        renderer_env,
        cell_size=args.cell_size,
        log_provider=ui.get_logs,
        status_provider=status_provider,
        fleet_provider=fleet_provider,
        state_lock=snapshot.lock,
    )
    renderer.run()


if __name__ == "__main__":
    main()
