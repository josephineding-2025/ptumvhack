from agent.orchestrator import AgentConfig, LocalToolClient, SwarmOrchestrator
from models.drone_state import DroneStatus
from server.fastmcp_bridge import env


def reset_environment() -> None:
    env.drones.clear()
    env.survivors.clear()
    env.searched_cells.clear()
    env.found_survivors.clear()
    env.seed_default_scenario()


def test_mission_status_exposes_search_and_offline_details() -> None:
    reset_environment()
    env.move_drone("DR-01", 3, 3)
    env.scan_sector("DR-01")
    env.set_offline("DR-02")

    status = env.get_mission_status()

    assert [3, 3] in status["searched_positions"]
    assert [3, 3] in status["found_survivor_positions"]
    assert "DR-02" in status["offline_drone_ids"]
    assert status["total_survivors"] == 5


def test_orchestrator_finds_survivor_and_rebalances_after_failure() -> None:
    reset_environment()
    orchestrator = SwarmOrchestrator(tool_client=LocalToolClient())
    try:
        env.set_offline("DR-04")
        result = orchestrator.run_continuous_mission(iterations=8)
    finally:
        orchestrator.close()

    thinking = [entry["message"] for entry in result["log"] if entry["type"] == "thinking"]

    assert env.searched_cells
    assert env.found_survivors
    assert any("went offline" in line for line in thinking)
    assert any("detected a survivor signature" in line for line in thinking)


def test_critical_battery_forces_immediate_base_return() -> None:
    reset_environment()
    env.move_drone("DR-01", 5, 0)
    env.drones["DR-01"].battery = 14
    env.drones["DR-01"].status = DroneStatus.SEARCHING
    env.set_offline("DR-02")
    env.set_offline("DR-03")
    env.set_offline("DR-04")

    orchestrator = SwarmOrchestrator(tool_client=LocalToolClient())
    try:
        orchestrator.run_continuous_mission(iterations=1)
    finally:
        orchestrator.close()

    assert env.drones["DR-01"].location == (0, 0)
    assert env.drones["DR-01"].status == DroneStatus.CHARGING


def test_battery_band_controls_near_vs_far_sector_assignment() -> None:
    reset_environment()
    env.set_offline("DR-02")
    env.set_offline("DR-03")
    env.set_offline("DR-04")

    near_config = AgentConfig(scan_after_move=False)
    env.drones["DR-01"].battery = 25
    env.drones["DR-01"].location = (0, 0)
    orchestrator_near = SwarmOrchestrator(config=near_config, tool_client=LocalToolClient())
    try:
        orchestrator_near.run_continuous_mission(iterations=1)
    finally:
        orchestrator_near.close()
    near_point = env.drones["DR-01"].location
    near_distance = abs(near_point[0]) + abs(near_point[1])

    reset_environment()
    env.set_offline("DR-02")
    env.set_offline("DR-03")
    env.set_offline("DR-04")
    env.drones["DR-01"].battery = 80
    env.drones["DR-01"].location = (0, 0)
    orchestrator_far = SwarmOrchestrator(config=near_config, tool_client=LocalToolClient())
    try:
        orchestrator_far.run_continuous_mission(iterations=1)
    finally:
        orchestrator_far.close()
    far_point = env.drones["DR-01"].location
    far_distance = abs(far_point[0]) + abs(far_point[1])

    assert near_distance <= 6
    assert far_distance >= 13


def test_base_drone_keeps_charging_until_dispatch_ready() -> None:
    reset_environment()
    env.drones["DR-01"].battery = 20
    env.drones["DR-01"].location = (0, 0)
    env.drones["DR-01"].status = DroneStatus.IDLE

    status_after_tick = env.get_battery_status("DR-01")

    assert status_after_tick["battery"] == 20
    assert status_after_tick["status"] == DroneStatus.CHARGING.value

    status_after_charge = env.get_battery_status("DR-01")

    assert status_after_charge["battery"] == 25
    assert status_after_charge["status"] == DroneStatus.CHARGING.value

    env.drones["DR-01"].battery = 20
    env.drones["DR-01"].location = (0, 0)
    env.drones["DR-01"].status = DroneStatus.CHARGING

    charging_status = env.get_battery_status("DR-01")

    assert charging_status["battery"] == 25
    assert charging_status["status"] == DroneStatus.CHARGING.value

    env.drones["DR-01"].battery = 20
    env.drones["DR-01"].status = DroneStatus.IDLE

    move_message = env.move_drone("DR-01", 4, 4)

    assert "still charging at base" in move_message
    assert env.drones["DR-01"].status == DroneStatus.CHARGING

    env.drones["DR-01"].battery = 100
    env.drones["DR-01"].status = DroneStatus.IDLE

    launch_message = env.move_drone("DR-01", 4, 4)

    assert "accepted waypoint" in launch_message
    assert env.drones["DR-01"].status == DroneStatus.SEARCHING


def test_mission_ends_and_returns_all_drones_when_survivors_found() -> None:
    reset_environment()
    env.found_survivors = set(env.survivors)
    env.move_drone("DR-01", 4, 4)
    env.move_drone("DR-02", 5, 5)
    env.move_drone("DR-03", 6, 6)
    env.move_drone("DR-04", 7, 7)

    orchestrator = SwarmOrchestrator(tool_client=LocalToolClient())
    try:
        result = orchestrator.run_continuous_mission(iterations=1)
    finally:
        orchestrator.close()

    assert result["status"] == "COMPLETE"
    assert env.drones["DR-01"].location == (0, 0)
    assert env.drones["DR-02"].location == (0, 0)
    assert env.drones["DR-03"].location == (0, 0)
    assert env.drones["DR-04"].location == (0, 0)


def test_full_grid_scan_completes_and_recalls_all_drones() -> None:
    reset_environment()
    for x in range(env.width):
        for y in range(env.height):
            env.searched_cells.add((x, y))
    env.move_drone("DR-01", 8, 0)
    env.move_drone("DR-02", 0, 8)
    env.move_drone("DR-03", 6, 6)
    env.move_drone("DR-04", 5, 4)

    orchestrator = SwarmOrchestrator(tool_client=LocalToolClient())
    try:
        result = orchestrator.run_continuous_mission(iterations=1)
    finally:
        orchestrator.close()

    assert result["status"] == "COMPLETE"
    assert env.drones["DR-01"].location == (0, 0)
    assert env.drones["DR-02"].location == (0, 0)
    assert env.drones["DR-03"].location == (0, 0)
    assert env.drones["DR-04"].location == (0, 0)
