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
    _ensure_mcp_ready()
    # Guard against duplicate registration.
    if getattr(register_tools, "_registered", False):
        return

    @mcp.tool()
    def mcp_list_drones() -> list[dict]:
        return list_drones()

    @mcp.tool()
    def mcp_move_to(drone_id: str, x: int, y: int) -> str:
        return move_to(drone_id, x, y)

    @mcp.tool()
    def mcp_get_battery_status(drone_id: str) -> dict:
        return get_battery_status(drone_id)

    @mcp.tool()
    def mcp_thermal_scan(drone_id: str) -> str:
        return thermal_scan(drone_id)

    @mcp.tool()
    def mcp_get_mission_status() -> dict:
        return get_mission_status()

    register_tools._registered = True  # type: ignore[attr-defined]


def main() -> None:
    _ensure_mcp_ready()
    register_tools()
    mcp.run()


if __name__ == "__main__":
    main()
