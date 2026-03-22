from sim.environment import SimulationEnvironment

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore


env = SimulationEnvironment()
mcp = FastMCP("drone_promax") if FastMCP else None


def _ensure_mcp_ready() -> None:
    if mcp is None:
        raise RuntimeError("FastMCP is not available. Install dependencies first.")


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _err(code: str, message: str, *, details: object | None = None) -> dict:
    payload: dict = {"ok": False, "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def get_active_fleet() -> list[dict]:
    return env.get_active_fleet()


def list_drones() -> dict:
    """Required MCP tool: list_drones(). Always returns JSON."""
    try:
        # Case-study required discovery call: the agent must discover active drones dynamically.
        drones = env.get_active_fleet()
        return _ok({"drones": drones})
    except Exception as e:  # pragma: no cover
        return _err("internal_error", "Failed to list drones.", details={"exception": type(e).__name__})


def move_to(drone_id: str, x: int, y: int) -> dict:
    """Required MCP tool: move_to(drone_id, x, y). Assigns waypoint; edge agent executes path."""
    try:
        message = env.move_drone(drone_id, x, y)
        status = env.get_battery_status(drone_id)
        return _ok({"message": message, "battery_status": status})
    except KeyError as e:
        return _err("unknown_drone", str(e))
    except ValueError as e:
        return _err("out_of_bounds", str(e), details={"x": x, "y": y})
    except Exception as e:  # pragma: no cover
        return _err("internal_error", "Failed to move drone.", details={"exception": type(e).__name__})


def thermal_scan(drone_id: str) -> dict:
    """Required MCP tool: thermal_scan(drone_id). Always returns JSON."""
    try:
        message = env.scan_sector(drone_id)
        status = env.get_battery_status(drone_id)
        detected = "detected" in message.lower()
        return _ok({"message": message, "detected": detected, "battery_status": status})
    except KeyError as e:
        return _err("unknown_drone", str(e))
    except Exception as e:  # pragma: no cover
        return _err("internal_error", "Failed to thermal scan.", details={"exception": type(e).__name__})


def get_battery_status(drone_id: str) -> dict:
    """Required MCP tool: get_battery_status(drone_id). Always returns JSON."""
    try:
        return _ok(env.get_battery_status(drone_id))
    except KeyError as e:
        return _err("unknown_drone", str(e))
    except Exception as e:  # pragma: no cover
        return _err("internal_error", "Failed to get battery status.", details={"exception": type(e).__name__})


def get_mission_status() -> dict:
    try:
        return _ok(env.get_mission_status())
    except Exception as e:  # pragma: no cover
        return _err("internal_error", "Failed to get mission status.", details={"exception": type(e).__name__})


def set_drone_offline(drone_id: str) -> dict:
    """Optional MCP tool: set_drone_offline(drone_id) for simulation fault injection."""
    try:
        env.set_offline(drone_id)
        return _ok({"message": f"{drone_id} set to OFFLINE", "drone_id": drone_id})
    except KeyError as e:
        return _err("unknown_drone", str(e))
    except Exception as e:  # pragma: no cover
        return _err("internal_error", "Failed to set drone offline.", details={"exception": type(e).__name__})


def register_tools() -> None:
    _ensure_mcp_ready()
    # Guard against duplicate registration.
    if getattr(register_tools, "_registered", False):
        return

    # IMPORTANT: expose exact required tool names (SPEC.md §4).
    @mcp.tool()
    def list_drones() -> dict:  # type: ignore[no-redef]
        return globals()["list_drones"]()

    @mcp.tool()
    def move_to(drone_id: str, x: int, y: int) -> dict:  # type: ignore[no-redef]
        return globals()["move_to"](drone_id, x, y)

    @mcp.tool()
    def get_battery_status(drone_id: str) -> dict:  # type: ignore[no-redef]
        return globals()["get_battery_status"](drone_id)

    @mcp.tool()
    def thermal_scan(drone_id: str) -> dict:  # type: ignore[no-redef]
        return globals()["thermal_scan"](drone_id)

    @mcp.tool()
    def get_mission_status() -> dict:  # type: ignore[no-redef]
        return globals()["get_mission_status"]()

    @mcp.tool()
    def set_drone_offline(drone_id: str) -> dict:  # type: ignore[no-redef]
        return globals()["set_drone_offline"](drone_id)

    register_tools._registered = True  # type: ignore[attr-defined]


def main() -> None:
    _ensure_mcp_ready()
    register_tools()
    mcp.run()


if __name__ == "__main__":
    main()
