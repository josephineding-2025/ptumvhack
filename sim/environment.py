from dataclasses import dataclass, field
from typing import Dict, Set, Tuple

from models.drone_state import DroneState, DroneStatus


GridPoint = Tuple[int, int]


@dataclass
class SimulationEnvironment:
    width: int = 20
    height: int = 20
    base_station: GridPoint = (0, 0)
    drones: Dict[str, DroneState] = field(default_factory=dict)
    survivors: Set[GridPoint] = field(default_factory=set)
    searched_cells: Set[GridPoint] = field(default_factory=set)
    found_survivors: Set[GridPoint] = field(default_factory=set)

    def add_drone(self, drone: DroneState) -> None:
        self.drones[drone.drone_id] = drone

    def set_offline(self, drone_id: str) -> None:
        drone = self.drones[drone_id]
        drone.status = DroneStatus.OFFLINE

    def get_active_fleet(self) -> list[dict]:
        return [d.to_public_dict() for d in self.drones.values() if d.is_online()]

    def move_drone(self, drone_id: str, target_x: int, target_y: int) -> str:
        # TODO(Member 2): Replace with stepwise movement + timing model.
        drone = self.drones[drone_id]
        distance = abs(drone.location[0] - target_x) + abs(drone.location[1] - target_y)
        drone.location = (target_x, target_y)
        drone.battery -= distance
        drone.clamp_battery()
        drone.status = DroneStatus.SEARCHING if drone.battery > 15 else DroneStatus.CHARGING
        return f"{drone_id} moving to [{target_x}, {target_y}]. Estimated arrival: {distance} seconds."

    def scan_sector(self, drone_id: str) -> str:
        # TODO(Member 2): Expand to radius-based scanning if needed.
        drone = self.drones[drone_id]
        drone.battery -= 2
        drone.clamp_battery()
        self.searched_cells.add(drone.location)
        if drone.location in self.survivors:
            self.found_survivors.add(drone.location)
            return "Scan complete. 1 thermal signature detected!"
        return "No signatures."

    def get_mission_status(self) -> dict:
        total_cells = self.width * self.height
        return {
            "grid_size": [self.width, self.height],
            "searched_cells": len(self.searched_cells),
            "coverage_ratio": len(self.searched_cells) / total_cells if total_cells else 0,
            "survivors_found": len(self.found_survivors),
            "active_drones": len(self.get_active_fleet()),
        }
