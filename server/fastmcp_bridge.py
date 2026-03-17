from sim.environment import SimulationEnvironment

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore


env = SimulationEnvironment()
mcp = FastMCP("AegisSwarm") if FastMCP else None


def _ensure_mcp_ready() -> None:
    if mcp is None:
        raise RuntimeError("FastMCP is not available. Install dependencies first.")


def get_active_fleet() -> list[dict]:
    return env.get_active_fleet()


def list_drones() -> list[dict]:
    # Case-study required discovery call: the agent must discover active drones dynamically.
    return env.get_active_fleet()


def move_drone(drone_id: str, target_x: int, target_y: int) -> str:
    return env.move_drone(drone_id, target_x, target_y)


def move_to(drone_id: str, x: int, y: int) -> str:
    # Case-study naming variant.
    return env.move_drone(drone_id, x, y)


def scan_sector(drone_id: str) -> str:
    return env.scan_sector(drone_id)


def thermal_scan(drone_id: str) -> str:
    # Case-study naming variant.
    return env.scan_sector(drone_id)


def get_battery_status(drone_id: str) -> dict:
    return env.get_battery_status(drone_id)


def get_mission_status() -> dict:
    return env.get_mission_status()


def register_tools() -> None:
    # TODO(Member 1): Decorate/export MCP tools using FastMCP APIs.
    # Minimum required by case study:
    # - discovery: list_drones()
    # - movement: move_to(drone_id, x, y)
    # - telemetry: get_battery_status(drone_id)
    # - sensing: thermal_scan(drone_id)
    _ensure_mcp_ready()


def main() -> None:
    # TODO(Member 1): register tools and run localhost server.
    _ensure_mcp_ready()
    register_tools()
    raise NotImplementedError("FastMCP server run loop scaffold only.")


if __name__ == "__main__":
    main()
