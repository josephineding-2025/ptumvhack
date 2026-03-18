from agent.orchestrator import SwarmOrchestrator
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


def test_orchestrator_finds_survivor_and_rebalances_after_failure() -> None:
    reset_environment()
    orchestrator = SwarmOrchestrator()
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
