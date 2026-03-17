import logging
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from agent.prompts import MISSION_START_PROMPT, SYSTEM_PROMPT, user_command_prompt
from server import fastmcp_bridge as tools

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
    startup_waypoints: tuple[tuple[int, int], ...] = ((4, 4), (14, 4), (4, 14), (14, 14))


class LocalToolClient:
    def list_drones(self) -> dict:
        return tools.list_drones()

    def move_to(self, drone_id: str, x: int, y: int) -> dict:
        return tools.move_to(drone_id, x, y)

    def get_battery_status(self, drone_id: str) -> dict:
        return tools.get_battery_status(drone_id)

    def thermal_scan(self, drone_id: str) -> dict:
        return tools.thermal_scan(drone_id)

    def get_mission_status(self) -> dict:
        return tools.get_mission_status()


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

    def run_continuous_mission(self, iterations: int = 20) -> dict[str, Any]:
        import time

        self._log_thinking("Starting continuous Search and Rescue mission loop.")
        
        for i in range(iterations):
            # 1. Discover Fleet
            fleet = self.tools.list_drones()
            if not fleet.get("ok"):
                break
            
            online_drones = fleet["data"]["drones"]
            if not online_drones:
                self._log_thinking("No online drones available. Waiting...")
                time.sleep(2)
                continue

            # 2. Check Mission Progress
            stats = self.tools.get_mission_status()
            if stats.get("ok"):
                coverage = stats["data"]["coverage_ratio"]
                self._log_thinking(f"Iteration {i+1}/{iterations}. Current Coverage: {coverage*100:.1f}%.")
                if coverage >= 0.95:
                    self._log_thinking("Mission Objective Achieved: High coverage reached.")
                    break

            # 3. Process Each Drone
            for drone in online_drones:
                drone_id = drone["id"]
                battery = drone["battery"]
                current_loc = drone["location"]

                # Battery Recall Logic
                if battery <= self.config.low_battery_threshold:
                    if current_loc != [0, 0]:
                        self._log_thinking(f"Drone {drone_id} battery low ({battery}%). Recalling to base.")
                        self.tools.move_to(drone_id, 0, 0)
                    else:
                        self._log_thinking(f"Drone {drone_id} is charging at base.")
                    continue

                # Search Logic: Move to a random nearby unscanned waypoint or just cycle through pattern
                # For simplicity in this demo, we'll use a spiral/grid pattern based on drone index and time
                target_x = (int(time.time() * 2) + int(drone_id[-1])) % 20
                target_y = (int(time.time()) + int(drone_id[-1]) * 3) % 20
                
                self._log_thinking(f"Drone {drone_id} ({battery}%): Moving to search sector [{target_x}, {target_y}].")
                self.tools.move_to(drone_id, target_x, target_y)
                
                self._log_thinking(f"Drone {drone_id}: Executing thermal scan at target.")
                scan_result = self.tools.thermal_scan(drone_id)
                if "1 thermal signature" in scan_result.get("data", {}).get("message", ""):
                    self._log_thinking(f"CRITICAL: Drone {drone_id} detected a survivor signature!")

            time.sleep(1)

        return {
            "status": "mission_paused_or_completed",
            "log": self.mission_log,
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
    import threading
    from sim.pygame_renderer import PygameRenderer
    from server.fastmcp_bridge import env

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    orchestrator = SwarmOrchestrator()
    
    # Run agent in background so Pygame can take the main thread (required on MacOS)
    def run_agent():
        result = orchestrator.run_continuous_mission(iterations=50)
        print(f"\n[{result['status']}] log_entries={len(result['log'])}")

    agent_thread = threading.Thread(target=run_agent, daemon=True)
    agent_thread.start()

    # Pygame window blocking call
    renderer = PygameRenderer(env)
    renderer.run()


if __name__ == "__main__":
    main()
