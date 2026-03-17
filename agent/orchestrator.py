import logging
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from agent.prompts import MISSION_START_PROMPT, SYSTEM_PROMPT, user_command_prompt
from server import fastmcp_bridge as tools

logger = logging.getLogger("aegis.orchestrator")


class ToolClient(Protocol):
    def list_drones(self) -> list[dict]: ...
    def move_to(self, drone_id: str, x: int, y: int) -> str: ...
    def get_battery_status(self, drone_id: str) -> dict: ...
    def thermal_scan(self, drone_id: str) -> str: ...


@dataclass
class AgentConfig:
    low_battery_threshold: int = 15
    startup_waypoints: tuple[tuple[int, int], ...] = ((4, 4), (14, 4), (4, 14), (14, 14))


class LocalToolClient:
    def list_drones(self) -> list[dict]:
        return tools.list_drones()

    def move_to(self, drone_id: str, x: int, y: int) -> str:
        return tools.move_to(drone_id, x, y)

    def get_battery_status(self, drone_id: str) -> dict:
        return tools.get_battery_status(drone_id)

    def thermal_scan(self, drone_id: str) -> str:
        return tools.thermal_scan(drone_id)


class SwarmOrchestrator:
    def __init__(self, config: AgentConfig | None = None, tool_client: ToolClient | None = None) -> None:
        self.config = config or AgentConfig()
        self.tools = tool_client or LocalToolClient()
        self.mission_log: list[dict[str, Any]] = []

    def _log_thinking(self, message: str) -> None:
        thinking = f"<thinking>{message}</thinking>"
        logger.info(thinking)
        self.mission_log.append({"type": "thinking", "message": thinking})

    def _record_action(self, tool_name: str, result: Any) -> None:
        self.mission_log.append({"type": "tool", "tool": tool_name, "result": result})

    def _assign_waypoints(self, drone_ids: Iterable[str]) -> list[tuple[str, tuple[int, int]]]:
        assignments: list[tuple[str, tuple[int, int]]] = []
        waypoints = self.config.startup_waypoints
        for idx, drone_id in enumerate(drone_ids):
            assignments.append((drone_id, waypoints[idx % len(waypoints)]))
        return assignments

    def run_startup_mission(self) -> dict[str, Any]:
        self._log_thinking(
            "Discover all active drones first, then assign nearest unscanned waypoints while keeping battery above recall threshold."
        )
        fleet = self.tools.list_drones()
        self._record_action("list_drones", fleet)

        online_ids = [d["id"] for d in fleet]
        assignments = self._assign_waypoints(online_ids)
        for drone_id, waypoint in assignments:
            battery = self.tools.get_battery_status(drone_id)
            self._record_action("get_battery_status", battery)
            if battery["battery"] <= self.config.low_battery_threshold:
                self._log_thinking(
                    f"Drone {drone_id} is at {battery['battery']}%. Recall to base to avoid mid-sector failure."
                )
                move_result = self.tools.move_to(drone_id, 0, 0)
                self._record_action("move_to", move_result)
                continue

            self._log_thinking(
                f"Drone {drone_id} has sufficient battery ({battery['battery']}%). Move to sector waypoint {waypoint}."
            )
            move_result = self.tools.move_to(drone_id, waypoint[0], waypoint[1])
            self._record_action("move_to", move_result)

            self._log_thinking(f"Drone {drone_id} arrived at {waypoint}; execute thermal scan for survivor signal.")
            scan_result = self.tools.thermal_scan(drone_id)
            self._record_action("thermal_scan", scan_result)

        return {
            "system_prompt": SYSTEM_PROMPT,
            "startup_prompt": MISSION_START_PROMPT,
            "log": self.mission_log,
            "status": "startup_completed",
        }

    def handle_user_command(self, command: str) -> dict[str, Any]:
        self._log_thinking(
            "Interpret user intent as sector objective, then continue MCP-only actions with battery/coverage checks."
        )
        return {
            "prompt": user_command_prompt(command),
            "status": "accepted",
            "mission_log_entries": len(self.mission_log),
        }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    orchestrator = SwarmOrchestrator()
    result = orchestrator.run_startup_mission()
    print(result["status"])
    print(f"log_entries={len(result['log'])}")


if __name__ == "__main__":
    main()
