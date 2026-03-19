import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.prompts import user_command_prompt

logger = logging.getLogger("aegis.orchestrator")


class ToolClient(Protocol):
    def list_drones(self) -> dict: ...
    def move_to(self, drone_id: str, x: int, y: int) -> dict: ...
    def get_battery_status(self, drone_id: str) -> dict: ...
    def thermal_scan(self, drone_id: str) -> dict: ...
    def get_mission_status(self) -> dict: ...


@dataclass
class AgentConfig:
    low_battery_threshold: int = 15
    caution_battery_threshold: int = 30
    scan_after_move: bool = True


class LocalToolClient:
    # Debug-only fallback. Default runtime path should use MCPToolClient.
    def list_drones(self) -> dict:
        from server import fastmcp_bridge as tools
        return tools.list_drones()

    def move_to(self, drone_id: str, x: int, y: int) -> dict:
        from server import fastmcp_bridge as tools
        return tools.move_to(drone_id, x, y)

    def get_battery_status(self, drone_id: str) -> dict:
        from server import fastmcp_bridge as tools
        return tools.get_battery_status(drone_id)

    def thermal_scan(self, drone_id: str) -> dict:
        from server import fastmcp_bridge as tools
        return tools.thermal_scan(drone_id)

    def get_mission_status(self) -> dict:
        from server import fastmcp_bridge as tools
        return tools.get_mission_status()


class MCPToolClient:
    def __init__(
        self,
        mcp_command: str | None = None,
        mcp_args: tuple[str, ...] | None = None,
    ) -> None:
        self._runner = asyncio.Runner()
        default_python = sys.executable or "python"
        configured_command = mcp_command or os.getenv("MCP_COMMAND", default_python)
        if configured_command.strip().lower() == "python":
            configured_command = default_python
        self._client = MultiServerMCPClient(
            {
                "aegis_swarm": {
                    "transport": "stdio",
                    # Use the active interpreter by default to avoid PATH/alias issues on Windows.
                    "command": configured_command,
                    "args": list(
                        mcp_args
                        or tuple(os.getenv("MCP_ARGS", "-m server.fastmcp_bridge").split())
                    ),
                }
            }
        )
        self._tools: dict[str, Any] = {}
        self._runner.run(self._initialize())

    async def _initialize(self) -> None:
        loaded_tools = await self._client.get_tools()
        self._tools = {tool.name: tool for tool in loaded_tools}
        required = {"list_drones", "move_to", "get_battery_status", "thermal_scan", "get_mission_status"}
        missing = required - self._tools.keys()
        if missing:
            raise RuntimeError(f"MCP server missing required tools: {sorted(missing)}")

    @staticmethod
    def _normalize_response(raw: Any) -> dict:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, dict) and "text" in first:
                return json.loads(first["text"])
        raise RuntimeError(f"Unexpected MCP response format: {type(raw).__name__}")

    def _invoke(self, name: str, payload: dict | None = None) -> dict:
        if name not in self._tools:
            raise RuntimeError(f"MCP tool not available: {name}")
        raw = self._runner.run(self._tools[name].ainvoke(payload or {}))
        return self._normalize_response(raw)

    def close(self) -> None:
        self._runner.close()

    def list_drones(self) -> dict:
        return self._invoke("list_drones")

    def move_to(self, drone_id: str, x: int, y: int) -> dict:
        return self._invoke("move_to", {"drone_id": drone_id, "x": x, "y": y})

    def get_battery_status(self, drone_id: str) -> dict:
        return self._invoke("get_battery_status", {"drone_id": drone_id})

    def thermal_scan(self, drone_id: str) -> dict:
        return self._invoke("thermal_scan", {"drone_id": drone_id})

    def get_mission_status(self) -> dict:
        return self._invoke("get_mission_status")


class SwarmOrchestrator:
    def __init__(self, config: AgentConfig | None = None, tool_client: ToolClient | None = None) -> None:
        self.config = config or AgentConfig()
        self.tools = tool_client or MCPToolClient()
        self.mission_log: list[dict[str, Any]] = []
        self._known_offline: set[str] = set()
        self._current_objective: str = ""

    def _log_thinking(self, message: str) -> None:
        thinking = f"<thinking>{message}</thinking>"
        logger.info(thinking)
        self.mission_log.append({"type": "thinking", "message": thinking})

    def _record_action(self, tool_name: str, result: Any) -> None:
        self.mission_log.append({"type": "tool", "tool": tool_name, "result": result})

    @staticmethod
    def _point_key(point: list[int] | tuple[int, int]) -> tuple[int, int]:
        return (int(point[0]), int(point[1]))

    @staticmethod
    def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _step_toward(current: tuple[int, int], target: tuple[int, int], max_steps: int) -> tuple[int, int]:
        x, y = current
        tx, ty = target
        remaining = max(0, max_steps)
        while remaining > 0 and (x, y) != (tx, ty):
            if x < tx:
                x += 1
            elif x > tx:
                x -= 1
            elif y < ty:
                y += 1
            elif y > ty:
                y -= 1
            remaining -= 1
        return (x, y)

    @staticmethod
    def _extract_data(response: dict) -> dict:
        if not response.get("ok"):
            return {}
        data = response.get("data")
        return data if isinstance(data, dict) else {}

    def _announce_new_offline_drones(self, offline_ids: set[str]) -> None:
        new_offline = sorted(offline_ids - self._known_offline)
        for drone_id in new_offline:
            self._log_thinking(f"Drone {drone_id} went offline. Rebalancing remaining search sectors.")
        self._known_offline = set(offline_ids)

    @staticmethod
    def _sector_bounds(index: int, total: int, width: int) -> tuple[int, int]:
        start = (index * width) // total
        end = ((index + 1) * width) // total
        return start, max(start + 1, end)

    def _build_search_candidates(
        self,
        current: tuple[int, int],
        searched: set[tuple[int, int]],
        occupied: set[tuple[int, int]],
        width: int,
        height: int,
        sector_start: int,
        sector_end: int,
        iteration: int,
        drone_seed: int,
        battery: int,
        prefer_near_base: bool | None,
    ) -> list[tuple[int, int]]:
        sector_cells: list[tuple[int, int]] = []
        global_cells: list[tuple[int, int]] = []
        base = (0, 0)
        near_limit = max(3, (width + height) // 6)
        far_limit = max(near_limit + 1, (width + height) // 3)
        for x in range(width):
            for y in range(height):
                point = (x, y)
                if point in searched or point == current or point in occupied:
                    continue
                travel_cost = self._distance(current, point)
                return_cost = self._distance(point, base)
                reserve_cost = travel_cost + return_cost + 2
                if reserve_cost >= battery:
                    continue
                base_distance = self._distance(point, base)
                if prefer_near_base is True and base_distance > near_limit:
                    continue
                if prefer_near_base is False and base_distance < far_limit:
                    continue
                if sector_start <= x < sector_end:
                    sector_cells.append(point)
                else:
                    global_cells.append(point)

        preferred = sector_cells or global_cells
        if not preferred and prefer_near_base is not None:
            return self._build_search_candidates(
                current=current,
                searched=searched,
                occupied=occupied,
                width=width,
                height=height,
                sector_start=sector_start,
                sector_end=sector_end,
                iteration=iteration,
                drone_seed=drone_seed,
                battery=battery,
                prefer_near_base=None,
            )
        if not preferred:
            return []

        phase = (iteration + drone_seed) % 4
        reverse_rows = phase in (1, 3)
        reverse_cols = phase in (2, 3)

        def sort_key(point: tuple[int, int]) -> tuple[int, int, int, int]:
            x, y = point
            row_bias = -y if reverse_rows else y
            col_bias = -x if reverse_cols else x
            return (
                self._distance(current, point),
                row_bias,
                col_bias,
                (x + y + drone_seed + iteration) % max(1, width + height),
            )

        preferred.sort(key=sort_key)
        return preferred[:8]

    def _select_target(
        self,
        drone: dict[str, Any],
        drones: list[dict[str, Any]],
        searched: set[tuple[int, int]],
        width: int,
        height: int,
        iteration: int,
        battery: int,
        prefer_near_base: bool | None,
    ) -> tuple[int, int] | None:
        ordered_ids = sorted(item["id"] for item in drones)
        drone_index = ordered_ids.index(drone["id"])
        current = self._point_key(drone["location"])
        occupied = {self._point_key(item["location"]) for item in drones if item["id"] != drone["id"]}
        sector_start, sector_end = self._sector_bounds(drone_index, len(ordered_ids), width)
        drone_seed = sum(ord(ch) for ch in drone["id"])
        candidates = self._build_search_candidates(
            current=current,
            searched=searched,
            occupied=occupied,
            width=width,
            height=height,
            sector_start=sector_start,
            sector_end=sector_end,
            iteration=iteration,
            drone_seed=drone_seed,
            battery=battery,
            prefer_near_base=prefer_near_base,
        )
        if not candidates:
            return None
        return candidates[(iteration + drone_index + drone_seed) % len(candidates)]

    def _try_local_low_battery_scan(
        self,
        drone_id: str,
        current: tuple[int, int],
        searched: set[tuple[int, int]],
        battery: int,
    ) -> bool:
        if current in searched:
            return False
        return_cost = self._distance(current, (0, 0))
        if battery <= return_cost + 2:
            return False
        self._log_thinking(
            f"Drone {drone_id} is low on battery but still has enough reserve to scan its current sector before returning."
        )
        scan_result = self.tools.thermal_scan(drone_id)
        self._record_action("thermal_scan", scan_result)
        return True

    def _return_to_base(
        self,
        drone_id: str,
        current: tuple[int, int],
        battery: int,
    ) -> None:
        if current == (0, 0):
            self._log_thinking(
                f"Drone {drone_id} is already at base, so it remains charging until it can rejoin the mission."
            )
            return
        next_step = self._step_toward(current, (0, 0), max_steps=max(1, battery))
        self._log_thinking(
            f"Drone {drone_id} battery is low, so it is taking the shortest safe step back to base at [{next_step[0]}, {next_step[1]}]."
        )
        move_result = self.tools.move_to(drone_id, next_step[0], next_step[1])
        self._record_action("move_to", move_result)

    def _recall_all_active_drones(self, online_drones: list[dict[str, Any]]) -> None:
        self._log_thinking("Recalling all active drones to base [0, 0] and finalizing mission state as COMPLETE.")
        for drone in online_drones:
            self._return_to_base(
                drone_id=drone["id"],
                current=self._point_key(drone["location"]),
                battery=int(drone["battery"]),
            )

    def _is_user_objective_met(self, mission_data: dict[str, Any]) -> bool:
        if not self._current_objective.strip():
            return False
        objective = self._current_objective.lower()
        coverage = float(mission_data.get("coverage_ratio", 0.0))
        all_survivors_found = bool(mission_data.get("all_survivors_found", False))

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
            return int(mission_data.get("survivors_found", 0)) > 0
        return False

    def run_continuous_mission(self, iterations: int = 20) -> dict[str, Any]:
        self._log_thinking("Blackout mission start. Discovering active fleet first so sector assignments stay MCP-driven.")
        mission_status = "mission_paused_or_completed"

        for i in range(iterations):
            # 1. Discover Fleet
            fleet = self.tools.list_drones()
            if not fleet.get("ok"):
                break

            online_drones = fleet["data"]["drones"]
            if not online_drones:
                self._log_thinking("No active drones are visible through MCP, so the swarm must wait and retry discovery.")
                time.sleep(2)
                continue

            # 2. Check Mission Progress
            stats = self.tools.get_mission_status()
            mission_data = self._extract_data(stats)
            if stats.get("ok"):
                coverage = mission_data.get("coverage_ratio", 0.0)
                survivors_found = int(mission_data.get("survivors_found", 0))
                total_survivors = int(mission_data.get("total_survivors", 0))
                self._log_thinking(
                    f"Coverage is {coverage*100:.1f}%, so I will keep expanding into unsearched sectors while preserving battery."
                )
                self._announce_new_offline_drones(set(mission_data.get("offline_drone_ids", [])))
                full_grid_scanned = coverage >= 1.0
                all_survivors_found = total_survivors > 0 and survivors_found >= total_survivors
                objective_met = self._is_user_objective_met(mission_data)
                if full_grid_scanned or all_survivors_found or objective_met:
                    self._log_thinking(
                        "Mission completion condition met. All active drones will return to base [0, 0], then mission state will be COMPLETE."
                    )
                    self._recall_all_active_drones(online_drones)
                    mission_status = "COMPLETE"
                    break
            else:
                mission_data = {}

            grid_w, grid_h = mission_data.get("grid_size", [20, 20])
            searched = {
                self._point_key(point)
                for point in mission_data.get("searched_positions", [])
                if isinstance(point, (list, tuple)) and len(point) == 2
            }

            # 3. Process Each Drone
            for drone in online_drones:
                drone_id = drone["id"]
                battery = drone["battery"]
                current_loc = drone["location"]
                current_point = self._point_key(current_loc)

                # Battery Recall Logic
                if battery < self.config.low_battery_threshold:
                    self._log_thinking(
                        f"Drone {drone_id} battery dropped below {self.config.low_battery_threshold}%, so it must return to base [0, 0] immediately."
                    )
                    self._return_to_base(drone_id, current_point, battery)
                    continue

                if battery < self.config.caution_battery_threshold:
                    self._log_thinking(
                        f"Drone {drone_id} battery is below {self.config.caution_battery_threshold}%, so it will search near base to preserve a safe return path."
                    )
                    prefer_near_base: bool | None = True
                else:
                    self._log_thinking(
                        f"Drone {drone_id} battery is above {self.config.caution_battery_threshold}%, so it can take farther sectors from base for wider coverage."
                    )
                    prefer_near_base = False

                target = self._select_target(
                    drone=drone,
                    drones=online_drones,
                    searched=searched,
                    width=int(grid_w),
                    height=int(grid_h),
                    iteration=i,
                    battery=battery,
                    prefer_near_base=prefer_near_base,
                )
                if target is None:
                    self._log_thinking(
                        f"Drone {drone_id} has no safe new sector that still leaves return reserve, so it starts heading back to base."
                    )
                    self._return_to_base(drone_id, current_point, battery)
                    continue

                target_x, target_y = target
                self._log_thinking(
                    f"Drone {drone_id} has {battery}% battery and a coverage gap near [{target_x}, {target_y}], so it takes that sector."
                )
                move_result = self.tools.move_to(drone_id, target_x, target_y)
                self._record_action("move_to", move_result)

                move_data = self._extract_data(move_result)
                applied = move_data.get("battery_status", {}).get("location", [target_x, target_y])
                if isinstance(applied, list) and len(applied) == 2:
                    searched.add(self._point_key(applied))

                if not self.config.scan_after_move:
                    continue

                self._log_thinking(
                    f"Drone {drone_id} reached a fresh sector, so I am confirming survivor presence with a thermal scan."
                )
                scan_result = self.tools.thermal_scan(drone_id)
                self._record_action("thermal_scan", scan_result)
                scan_data = self._extract_data(scan_result)
                if bool(scan_data.get("detected")):
                    detected_loc = scan_data.get("battery_status", {}).get("location", [target_x, target_y])
                    if not isinstance(detected_loc, list) or len(detected_loc) != 2:
                        detected_loc = [target_x, target_y]
                    self._log_thinking(
                        f"Drone {drone_id} detected a survivor signature at exact coordinates [{int(detected_loc[0])}, {int(detected_loc[1])}] and is continuing the search pattern."
                    )

            time.sleep(1)

        return {
            "status": mission_status,
            "log": self.mission_log,
        }

    def handle_user_command(self, command: str) -> dict[str, Any]:
        self._current_objective = command
        self._log_thinking(
            "Interpreting the user objective into MCP-only sector tasks with battery-aware and self-healing coordination."
        )
        return {
            "prompt": user_command_prompt(command),
            "status": "accepted",
            "mission_log_entries": len(self.mission_log),
        }

    def close(self) -> None:
        close_fn = getattr(self.tools, "close", None)
        if callable(close_fn):
            close_fn()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Aegis swarm orchestrator mission loop.")
    parser.add_argument("--iterations", type=int, default=50, help="Mission loop iterations.")
    parser.add_argument(
        "--tool-backend",
        choices=("mcp", "local"),
        default="mcp",
        help="Use MCP transport (default) or direct local calls for debug.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Render simulation UI (only supported with --tool-backend local).",
    )
    args = parser.parse_args()

    if args.render and args.tool_backend != "local":
        raise SystemExit("--render requires --tool-backend local (MCP backend runs in separate process).")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    tool_client: ToolClient = LocalToolClient() if args.tool_backend == "local" else MCPToolClient()
    orchestrator = SwarmOrchestrator(tool_client=tool_client)
    try:
        if args.render:
            import threading
            from sim.pygame_renderer import PygameRenderer
            from server.fastmcp_bridge import env

            def run_agent() -> None:
                result = orchestrator.run_continuous_mission(iterations=args.iterations)
                print(f"\n[{result['status']}] log_entries={len(result['log'])}")

            agent_thread = threading.Thread(target=run_agent, daemon=True)
            agent_thread.start()
            renderer = PygameRenderer(env)
            renderer.run()
        else:
            result = orchestrator.run_continuous_mission(iterations=args.iterations)
            print(f"[{result['status']}] log_entries={len(result['log'])}")
    finally:
        orchestrator.close()


if __name__ == "__main__":
    main()
