import asyncio
import json
import os
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient, load_mcp_tools


def normalize(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict) and "text" in first:
            return json.loads(first["text"])
    raise RuntimeError(f"Unexpected MCP response format: {type(raw).__name__}")


async def main() -> None:
    client = MultiServerMCPClient(
        {
            "aegis_swarm": {
                "transport": "stdio",
                "command": os.getenv("MCP_COMMAND", "python"),
                "args": os.getenv("MCP_ARGS", "-m server.fastmcp_bridge").split(),
            }
        }
    )

    async with client.session("aegis_swarm") as session:
        tools = await load_mcp_tools(session, server_name="aegis_swarm")
        by_name: dict[str, Any] = {tool.name: tool for tool in tools}
        required = ("list_drones", "move_to", "get_battery_status", "thermal_scan", "get_mission_status")
        missing = [name for name in required if name not in by_name]
        if missing:
            raise RuntimeError(f"Missing required MCP tools: {missing}")

        fleet = normalize(await by_name["list_drones"].ainvoke({}))
        print("list_drones:", fleet)
        if not fleet.get("ok") or not fleet["data"]["drones"]:
            raise RuntimeError("No active drones returned from list_drones.")

        drone_id = fleet["data"]["drones"][0]["id"]
        move = normalize(await by_name["move_to"].ainvoke({"drone_id": drone_id, "x": 1, "y": 1}))
        print("move_to:", move)
        battery = normalize(await by_name["get_battery_status"].ainvoke({"drone_id": drone_id}))
        print("get_battery_status:", battery)
        scan = normalize(await by_name["thermal_scan"].ainvoke({"drone_id": drone_id}))
        print("thermal_scan:", scan)
        status = normalize(await by_name["get_mission_status"].ainvoke({}))
        print("get_mission_status:", status)
        print("MCP smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
