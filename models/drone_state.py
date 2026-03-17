from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


class DroneStatus(str, Enum):
    IDLE = "IDLE"
    SEARCHING = "SEARCHING"
    CHARGING = "CHARGING"
    OFFLINE = "OFFLINE"


@dataclass
class DroneState:
    drone_id: str
    location: Tuple[int, int] = (0, 0)
    battery: int = 100
    status: DroneStatus = DroneStatus.IDLE
    assigned_sector: str | None = None
    metadata: dict = field(default_factory=dict)

    def clamp_battery(self) -> None:
        self.battery = max(0, min(100, int(self.battery)))

    def is_online(self) -> bool:
        return self.status != DroneStatus.OFFLINE

    def to_public_dict(self) -> dict:
        return {
            "id": self.drone_id,
            "battery": self.battery,
            "location": [self.location[0], self.location[1]],
            "status": self.status.value,
        }
