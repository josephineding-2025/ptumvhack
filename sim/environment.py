from dataclasses import dataclass, field
from typing import Dict, Set, Tuple

from models.drone_state import DroneState, DroneStatus


GridPoint = Tuple[int, int]


@dataclass
class SimulationEnvironment:
    width: int = 20
    height: int = 20
    base_station: GridPoint = (0, 0)
    move_cost_per_cell: int = 1
    scan_cost: int = 2
    recall_threshold: int = 15
    drones: Dict[str, DroneState] = field(default_factory=dict)
    survivors: Set[GridPoint] = field(default_factory=set)
    searched_cells: Set[GridPoint] = field(default_factory=set)
    found_survivors: Set[GridPoint] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.drones:
            self.seed_default_scenario()

    def seed_default_scenario(self) -> None:
        self.drones = {
            "DR-01": DroneState(drone_id="DR-01", location=self.base_station),
            "DR-02": DroneState(drone_id="DR-02", location=self.base_station),
            "DR-03": DroneState(drone_id="DR-03", location=self.base_station),
            "DR-04": DroneState(drone_id="DR-04", location=self.base_station),
        }
        self.survivors = {(3, 3), (9, 14), (15, 6)}

    @staticmethod
    def _serialize_points(points: Set[GridPoint]) -> list[list[int]]:
        return [[x, y] for x, y in sorted(points)]

    def _assert_known_drone(self, drone_id: str) -> DroneState:
        if drone_id not in self.drones:
            raise KeyError(f"Unknown drone_id: {drone_id}")
        return self.drones[drone_id]

    def _assert_in_bounds(self, x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            raise ValueError(f"Target [{x}, {y}] is outside grid {self.width}x{self.height}")

    def add_drone(self, drone: DroneState) -> None:
        self.drones[drone.drone_id] = drone

    def set_offline(self, drone_id: str) -> None:
        drone = self._assert_known_drone(drone_id)
        drone.status = DroneStatus.OFFLINE

    def get_active_fleet(self) -> list[dict]:
        return [d.to_public_dict() for d in self.drones.values() if d.is_online()]

    def get_battery_status(self, drone_id: str) -> dict:
        drone = self._assert_known_drone(drone_id)
        return {
            "id": drone.drone_id,
            "battery": drone.battery,
            "status": drone.status.value,
            "location": [drone.location[0], drone.location[1]],
        }

    def move_drone(self, drone_id: str, target_x: int, target_y: int) -> str:
        self._assert_in_bounds(target_x, target_y)
        drone = self._assert_known_drone(drone_id)
        if not drone.is_online():
            return f"{drone_id} is offline and cannot move."

        distance = abs(drone.location[0] - target_x) + abs(drone.location[1] - target_y)
        battery_cost = distance * self.move_cost_per_cell
        if drone.battery <= 0:
            drone.status = DroneStatus.CHARGING
            return f"{drone_id} has no battery and must charge."

        drone.location = (target_x, target_y)
        drone.battery -= battery_cost
        drone.clamp_battery()
        drone.apply_activity_status(self.recall_threshold)
        return (
            f"{drone_id} moved to [{target_x}, {target_y}] "
            f"(distance={distance}, cost={battery_cost}, battery={drone.battery}%)."
        )

    def scan_sector(self, drone_id: str) -> str:
        drone = self._assert_known_drone(drone_id)
        if not drone.is_online():
            return f"{drone_id} is offline and cannot scan."
        if drone.battery <= 0:
            drone.status = DroneStatus.CHARGING
            return f"{drone_id} has no battery and cannot scan."

        drone.battery -= self.scan_cost
        drone.clamp_battery()
        drone.apply_activity_status(self.recall_threshold)
        self.searched_cells.add(drone.location)

        if drone.location in self.survivors:
            self.found_survivors.add(drone.location)
            return "Scan complete. 1 thermal signature detected!"
        return "Scan complete. No signatures."

    def recall_drone(self, drone_id: str) -> str:
        drone = self._assert_known_drone(drone_id)
        if not drone.is_online():
            return f"{drone_id} is offline and cannot be recalled."
        return self.move_drone(drone_id, self.base_station[0], self.base_station[1])

    def get_mission_status(self) -> dict:
        total_cells = self.width * self.height
        offline_ids = sorted(
            drone.drone_id for drone in self.drones.values() if drone.status == DroneStatus.OFFLINE
        )
        return {
            "grid_size": [self.width, self.height],
            "searched_cells": len(self.searched_cells),
            "searched_positions": self._serialize_points(self.searched_cells),
            "coverage_ratio": len(self.searched_cells) / total_cells if total_cells else 0,
            "survivors_found": len(self.found_survivors),
            "found_survivor_positions": self._serialize_points(self.found_survivors),
            "active_drones": len(self.get_active_fleet()),
            "offline_drones": len(offline_ids),
            "offline_drone_ids": offline_ids,
            "total_drones": len(self.drones),
        }
