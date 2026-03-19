import math
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Set, Tuple

from models.drone_state import DroneState, DroneStatus

try:
    from mesa import Agent, Model
    from mesa.space import MultiGrid
except Exception as exc:  # pragma: no cover
    raise RuntimeError("Mesa is required. Install dependencies with tools/setup.ps1.") from exc


GridPoint = Tuple[int, int]


class DroneMesaAgent(Agent):
    def __init__(self, model: "SwarmMesaModel", drone_state: DroneState) -> None:
        try:
            super().__init__(model)
        except TypeError:
            # Mesa < 3.0 signature: Agent(unique_id, model)
            super().__init__(drone_state.drone_id, model)
        self.drone_state = drone_state
        self.pos = drone_state.location

    @property
    def drone_id(self) -> str:
        return self.drone_state.drone_id

    def waypoint(self) -> GridPoint | None:
        raw = self.drone_state.metadata.get("waypoint")
        if isinstance(raw, tuple) and len(raw) == 2:
            return int(raw[0]), int(raw[1])
        if isinstance(raw, list) and len(raw) == 2:
            return int(raw[0]), int(raw[1])
        return None

    def set_waypoint(self, point: GridPoint) -> None:
        self.drone_state.metadata["waypoint"] = (int(point[0]), int(point[1]))

    def clear_waypoint(self) -> None:
        self.drone_state.metadata.pop("waypoint", None)

    def _recent_positions(self) -> list[GridPoint]:
        raw = self.drone_state.metadata.get("recent_positions")
        if not isinstance(raw, list):
            return []
        cleaned: list[GridPoint] = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                cleaned.append((int(item[0]), int(item[1])))
        return cleaned

    def _remember_position(self, point: GridPoint) -> None:
        history = self._recent_positions()
        history.append((int(point[0]), int(point[1])))
        # Keep short tabu window to avoid oscillation, but still allow eventual revisits.
        self.drone_state.metadata["recent_positions"] = history[-8:]

    def _previous_position(self) -> GridPoint | None:
        history = self._recent_positions()
        if len(history) < 2:
            return None
        return history[-2]

    def _candidate_steps_toward(self, target: GridPoint) -> list[GridPoint]:
        x, y = self.drone_state.location
        tx, ty = target
        candidates: list[GridPoint] = []
        # Deterministic axis preference per drone to reduce synchronized corridor contention.
        prefer_y_first = (sum(ord(ch) for ch in self.drone_id) % 2) == 0
        primary = "y" if prefer_y_first else "x"
        secondary = "x" if prefer_y_first else "y"

        def step_axis(axis: str) -> None:
            if axis == "x":
                if x < tx:
                    candidates.append((x + 1, y))
                elif x > tx:
                    candidates.append((x - 1, y))
            else:
                if y < ty:
                    candidates.append((x, y + 1))
                elif y > ty:
                    candidates.append((x, y - 1))

        step_axis(primary)
        step_axis(secondary)
        # Small neighborhood fallback for local negotiation when direct lane is blocked.
        candidates.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

        deduped: list[GridPoint] = []
        seen: set[GridPoint] = set()
        for px, py in candidates:
            if (px, py) in seen:
                continue
            seen.add((px, py))
            if px < 0 or py < 0 or px >= self.model.width or py >= self.model.height:
                continue
            deduped.append((px, py))
        return deduped

    def _feasible_candidates(self, waypoint: GridPoint) -> list[GridPoint]:
        feasible: list[GridPoint] = []
        previous = self._previous_position()
        for candidate in self._candidate_steps_toward(waypoint):
            if previous is not None and candidate == previous:
                continue
            # Battery reserve policy: every step must preserve enough charge to reach base.
            post_battery = int(self.drone_state.battery) - int(self.model.move_cost_per_cell)
            if post_battery < 0:
                continue
            dist_to_base_after_step = abs(candidate[0] - self.model.base_station[0]) + abs(candidate[1] - self.model.base_station[1])
            if post_battery < dist_to_base_after_step:
                continue
            feasible.append(candidate)
        return feasible

    def propose_next_move(self, occupied_now: set[GridPoint]) -> GridPoint | None:
        # Edge autonomy: local battery policy overrides central waypoint when unsafe.
        if self.drone_state.battery <= self.model.recall_threshold and self.drone_state.location != self.model.base_station:
            self.set_waypoint(self.model.base_station)
        waypoint = self.waypoint()
        if waypoint is None:
            return None
        current = self.drone_state.location
        if current == waypoint:
            return None
        if self.drone_state.battery <= 0:
            return None
        feasible = self._feasible_candidates(waypoint)
        if waypoint != self.model.base_station:
            recent = set(self._recent_positions()[-6:])
            non_repeating = [candidate for candidate in feasible if candidate not in recent]
            if non_repeating:
                feasible = non_repeating
        for candidate in feasible:
            if candidate not in occupied_now:
                return candidate
        # If current waypoint is no longer safely reachable, edge agent switches to base autonomously.
        if waypoint != self.model.base_station:
            self.set_waypoint(self.model.base_station)
            feasible_base = self._feasible_candidates(self.model.base_station)
            for candidate in feasible_base:
                if candidate not in occupied_now:
                    return candidate
        return None

    def apply_post_move_status(self) -> None:
        if self.drone_state.status == DroneStatus.OFFLINE:
            return
        if self.drone_state.location == self.model.base_station:
            self.clear_waypoint()
            if self.drone_state.battery < self.model.dispatch_ready_threshold:
                self.drone_state.status = DroneStatus.CHARGING
            else:
                self.drone_state.status = DroneStatus.IDLE
            return
        # Off-base drones must stay mobile so they can return for recharge.
        self.drone_state.status = DroneStatus.SEARCHING


class SwarmMesaModel(Model):
    def __init__(
        self,
        width: int,
        height: int,
        base_station: GridPoint,
        move_cost_per_cell: int,
        recall_threshold: int,
        dispatch_ready_threshold: int,
    ) -> None:
        super().__init__()
        self.width = width
        self.height = height
        self.base_station = base_station
        self.move_cost_per_cell = move_cost_per_cell
        self.recall_threshold = recall_threshold
        self.dispatch_ready_threshold = dispatch_ready_threshold
        self.grid = MultiGrid(width=width, height=height, torus=False)
        self.drone_agents: dict[str, DroneMesaAgent] = {}
        self.tick_count: int = 0

    def add_drone(self, drone_state: DroneState) -> None:
        agent = DroneMesaAgent(self, drone_state)
        self.drone_agents[drone_state.drone_id] = agent
        self.grid.place_agent(agent, drone_state.location)
        drone_state.metadata.setdefault("last_move_tick", 0)
        agent._remember_position(drone_state.location)

    def set_waypoint(self, drone_id: str, point: GridPoint) -> None:
        self.drone_agents[drone_id].set_waypoint(point)

    def clear_waypoint(self, drone_id: str) -> None:
        self.drone_agents[drone_id].clear_waypoint()

    def _online_agents(self) -> Iterable[DroneMesaAgent]:
        for agent in self.drone_agents.values():
            if agent.drone_state.status != DroneStatus.OFFLINE:
                yield agent

    @staticmethod
    def _heading_from_vectors(vectors: list[tuple[int, int]]) -> str:
        if not vectors:
            return "east"
        sum_dx = sum(vector[0] for vector in vectors)
        sum_dy = sum(vector[1] for vector in vectors)
        if abs(sum_dx) >= abs(sum_dy):
            return "east" if sum_dx >= 0 else "west"
        return "south" if sum_dy >= 0 else "north"

    @staticmethod
    def _formation_offsets(heading: str, count: int, tick_count: int) -> list[GridPoint]:
        diagonal_patterns = {
            "east": [
                [(0, 0), (-1, -1), (-1, 1), (-2, -2), (-2, 0), (-2, 2), (-3, -1), (-3, 1)],
                [(0, 0), (-1, 0), (-2, -1), (-2, 1), (-3, -2), (-3, 0), (-3, 2), (-4, -1)],
            ],
            "west": [
                [(0, 0), (1, 1), (1, -1), (2, 2), (2, 0), (2, -2), (3, 1), (3, -1)],
                [(0, 0), (1, 0), (2, 1), (2, -1), (3, 2), (3, 0), (3, -2), (4, 1)],
            ],
            "south": [
                [(0, 0), (-1, -1), (1, -1), (-2, -2), (0, -2), (2, -2), (-1, -3), (1, -3)],
                [(0, 0), (0, -1), (-1, -2), (1, -2), (-2, -3), (0, -3), (2, -3), (-1, -4)],
            ],
            "north": [
                [(0, 0), (1, 1), (-1, 1), (2, 2), (0, 2), (-2, 2), (1, 3), (-1, 3)],
                [(0, 0), (0, 1), (1, 2), (-1, 2), (2, 3), (0, 3), (-2, 3), (1, 4)],
            ],
        }
        pattern_family = diagonal_patterns[heading]
        pattern = pattern_family[tick_count % len(pattern_family)]
        return pattern[:count]

    def _formation_targets(self, agents: list[DroneMesaAgent]) -> dict[str, GridPoint]:
        moving_agents = [agent for agent in agents if agent.waypoint() is not None]
        if not moving_agents:
            return {}
        heading_vectors: list[tuple[int, int]] = []
        for agent in moving_agents:
            waypoint = agent.waypoint()
            if waypoint is None:
                continue
            current = agent.drone_state.location
            heading_vectors.append((int(waypoint[0]) - int(current[0]), int(waypoint[1]) - int(current[1])))
        heading = self._heading_from_vectors(heading_vectors)

        def leader_key(agent: DroneMesaAgent) -> tuple[int, int, str]:
            x, y = agent.drone_state.location
            if heading == "east":
                return (x, -y, agent.drone_id)
            if heading == "west":
                return (-x, y, agent.drone_id)
            if heading == "south":
                return (y, -x, agent.drone_id)
            return (-y, x, agent.drone_id)

        leader = max(moving_agents, key=leader_key)
        leader_x, leader_y = leader.drone_state.location
        ordered_agents = [leader] + sorted(
            [agent for agent in moving_agents if agent.drone_id != leader.drone_id],
            key=lambda agent: agent.drone_id,
        )
        offsets = self._formation_offsets(heading, len(ordered_agents), self.tick_count)
        return {
            agent.drone_id: (leader_x + offset[0], leader_y + offset[1])
            for agent, offset in zip(ordered_agents, offsets, strict=False)
        }

    @staticmethod
    def _candidate_score(
        candidate: GridPoint,
        waypoint: GridPoint,
        formation_target: GridPoint | None,
        base_station: GridPoint,
    ) -> tuple[int, int, int, int, int]:
        formation_distance = (
            abs(candidate[0] - formation_target[0]) + abs(candidate[1] - formation_target[1])
            if formation_target is not None
            else 0
        )
        waypoint_distance = abs(candidate[0] - waypoint[0]) + abs(candidate[1] - waypoint[1])
        base_distance = abs(candidate[0] - base_station[0]) + abs(candidate[1] - base_station[1])
        return (formation_distance, waypoint_distance, -base_distance, candidate[1], candidate[0])

    def step(self) -> None:
        self.tick_count += 1
        online_agents = list(self._online_agents())
        occupied_now = {agent.drone_state.location for agent in online_agents}
        formation_targets = self._formation_targets(online_agents)
        proposed_targets: dict[str, list[GridPoint]] = {}
        formation_tolerance = 2
        for agent in online_agents:
            if agent.drone_state.status == DroneStatus.CHARGING:
                continue
            waypoint = agent.waypoint()
            if waypoint is None:
                agent.apply_post_move_status()
                continue
            if agent.drone_state.location == waypoint:
                # Reached assigned destination: stop and wait for next central wave.
                agent.clear_waypoint()
                agent.apply_post_move_status()
                continue
            candidates = agent._feasible_candidates(waypoint)  # noqa: SLF001 - local negotiation helper
            if not candidates and waypoint != self.base_station:
                agent.set_waypoint(self.base_station)
                candidates = agent._feasible_candidates(self.base_station)  # noqa: SLF001
            if not candidates:
                agent.apply_post_move_status()
                continue
            active_waypoint = agent.waypoint() or waypoint
            formation_target = formation_targets.get(agent.drone_id)
            candidates.sort(
                key=lambda candidate: self._candidate_score(
                    candidate,
                    active_waypoint,
                    formation_target,
                    self.base_station,
                )
            )
            if formation_target is not None:
                pattern_locked = [
                    candidate
                    for candidate in candidates
                    if abs(candidate[0] - formation_target[0]) + abs(candidate[1] - formation_target[1]) <= formation_tolerance
                ]
                if pattern_locked:
                    candidates = pattern_locked
            proposed_targets[agent.drone_id] = candidates

        # Deadlock-resistant local negotiation:
        # allow moving into a currently occupied cell when its occupants also intend to move.
        occupants: dict[GridPoint, set[str]] = {}
        for agent in online_agents:
            occupants.setdefault(agent.drone_state.location, set()).add(agent.drone_id)
        priority = sorted(
            [agent for agent in online_agents if agent.drone_id in proposed_targets],
            key=lambda a: (-int(a.drone_state.battery), a.drone_id),
        )
        approved_moves: dict[str, GridPoint] = {}
        reserved_targets: set[GridPoint] = set()
        moving_ids = set(proposed_targets.keys())
        for agent in priority:
            if agent.drone_id in approved_moves:
                continue
            for target in proposed_targets.get(agent.drone_id, []):
                # Prevent same-cell conflicts, except base can accept multiple drones.
                if target != self.base_station and target in reserved_targets:
                    continue
                if target == self.base_station:
                    approved_moves[agent.drone_id] = target
                    break
                blockers = occupants.get(target, set()) - {agent.drone_id}
                # If a blocker is stationary this tick, avoid that cell.
                if any(blocker not in moving_ids for blocker in blockers):
                    continue
                approved_moves[agent.drone_id] = target
                reserved_targets.add(target)
                break

        # Edge-side execution: one cell per tick + local battery drain.
        for drone_id, target in approved_moves.items():
            agent = self.drone_agents[drone_id]
            self.grid.move_agent(agent, target)
            agent.drone_state.location = target
            agent._remember_position(target)
            agent.drone_state.metadata["last_move_tick"] = int(self.tick_count)
            agent.drone_state.battery -= self.move_cost_per_cell
            agent.drone_state.clamp_battery()
            self._passive_thermal_update(agent.drone_id)
            self._mark_searched(agent.drone_state.location)
            if agent.drone_state.location == agent.waypoint():
                agent.clear_waypoint()
            agent.apply_post_move_status()

        for agent in self._online_agents():
            if agent.drone_id in approved_moves:
                continue
            self._passive_thermal_update(agent.drone_id)
            self._mark_searched(agent.drone_state.location)
            agent.apply_post_move_status()

    def _passive_thermal_update(self, drone_id: str) -> None:
        self.drone_agents[drone_id].drone_state.metadata["passive_thermal_tick"] = True

    def _mark_searched(self, _: GridPoint) -> None:
        # Hook implemented by SimulationEnvironment through model owner callback.
        return


@dataclass
class SimulationEnvironment:
    width: int = 20
    height: int = 20
    base_station: GridPoint = (0, 0)
    move_cost_per_cell: int = 1
    scan_cost: int = 2
    recall_threshold: int = 15
    dispatch_ready_threshold: int = 100
    charge_rate: int = 5
    edge_tick_interval_sec: float = 0.14
    drones: Dict[str, DroneState] = field(default_factory=dict)
    survivors: Set[GridPoint] = field(default_factory=set)
    searched_cells: Set[GridPoint] = field(default_factory=set)
    found_survivors: Set[GridPoint] = field(default_factory=set)
    tree_cells: Set[GridPoint] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.tree_cells:
            self.tree_cells = self._generate_tree_cells()
        self._model = SwarmMesaModel(
            width=self.width,
            height=self.height,
            base_station=self.base_station,
            move_cost_per_cell=self.move_cost_per_cell,
            recall_threshold=self.recall_threshold,
            dispatch_ready_threshold=self.dispatch_ready_threshold,
        )
        if not self.drones:
            self.seed_default_scenario()
        else:
            for drone in self.drones.values():
                self._model.add_drone(drone)
        self._model._mark_searched = self._mark_searched  # type: ignore[method-assign]
        self._last_edge_tick_ts = 0.0

    def _reset_model(self) -> None:
        self._model = SwarmMesaModel(
            width=self.width,
            height=self.height,
            base_station=self.base_station,
            move_cost_per_cell=self.move_cost_per_cell,
            recall_threshold=self.recall_threshold,
            dispatch_ready_threshold=self.dispatch_ready_threshold,
        )
        self._model._mark_searched = self._mark_searched  # type: ignore[method-assign]

    def seed_default_scenario(self) -> None:
        self.survivors = {(3, 3), (9, 14), (15, 6), (12, 12), (18, 2)}
        self.tree_cells = self._generate_tree_cells()
        self._reset_model()
        self.drones = {
            "DR-01": DroneState(drone_id="DR-01", location=self.base_station),
            "DR-02": DroneState(drone_id="DR-02", location=self.base_station),
            "DR-03": DroneState(drone_id="DR-03", location=self.base_station),
            "DR-04": DroneState(drone_id="DR-04", location=self.base_station),
        }
        for drone in self.drones.values():
            self._model.add_drone(drone)
            self._mark_searched(drone.location)

    def _generate_river_cells(self) -> Set[GridPoint]:
        river: Set[GridPoint] = set()
        for y in range(self.height):
            center = int(round(4 + 0.22 * y + 1.3 * math.sin(y * 0.55)))
            for dx in (-1, 0, 1):
                x = center + dx
                if 0 <= x < self.width:
                    river.add((x, y))
        return river

    def _generate_tree_cells(self) -> Set[GridPoint]:
        trees: Set[GridPoint] = set()
        river_cells = self._generate_river_cells()
        reserved = set(self.survivors) | {self.base_station} | river_cells
        cluster_centers = [(2, 15), (6, 4), (10, 16), (14, 8), (17, 13)]
        for x in range(self.width):
            for y in range(self.height):
                point = (x, y)
                if point in reserved:
                    continue
                if x <= 2 and y <= 2:
                    continue
                nearest_cluster = min(abs(x - cx) + abs(y - cy) for cx, cy in cluster_centers)
                scatter = (x * 13 + y * 17 + x * y * 5) % 19
                diagonal_bias = (x - 2 * y) % 11
                if nearest_cluster <= 2 and scatter in {0, 3, 7, 11, 14}:
                    trees.add(point)
                    continue
                if nearest_cluster <= 4 and diagonal_bias in {0, 1} and scatter in {2, 5, 9}:
                    trees.add(point)
                    continue
                if scatter == 0 and (x + y) % 3 == 0:
                    trees.add(point)
        return trees

    def is_tree_cell(self, point: GridPoint) -> bool:
        return (int(point[0]), int(point[1])) in self.tree_cells

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
        self._model.add_drone(drone)

    def set_offline(self, drone_id: str) -> None:
        drone = self._assert_known_drone(drone_id)
        drone.status = DroneStatus.OFFLINE
        self._model.clear_waypoint(drone_id)

    def _service_charging(self) -> None:
        for drone in self.drones.values():
            if drone.status != DroneStatus.CHARGING or drone.location != self.base_station:
                continue
            drone.battery = min(100, drone.battery + self.charge_rate)
            if drone.battery >= self.dispatch_ready_threshold:
                drone.status = DroneStatus.IDLE

    @staticmethod
    def _distance(a: GridPoint, b: GridPoint) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _sector_bounds(index: int, total: int, width: int) -> tuple[int, int]:
        start = (index * width) // total
        end = ((index + 1) * width) // total
        return start, max(start + 1, end)

    def _assign_autonomous_waypoints(self) -> None:
        total_cells = self.width * self.height
        coverage_ratio = len(self.searched_cells) / total_cells if total_cells else 0.0
        if coverage_ratio >= 1.0 or len(self.found_survivors) >= len(self.survivors):
            return

        drone_ids = sorted(self.drones.keys())
        for idx, drone_id in enumerate(drone_ids):
            drone = self.drones[drone_id]
            if not drone.is_online():
                continue
            agent = self._model.drone_agents[drone_id]
            if agent.waypoint() is not None:
                continue
            if drone.status == DroneStatus.CHARGING:
                continue
            if drone.battery <= self.recall_threshold and drone.location != self.base_station:
                self._model.set_waypoint(drone_id, self.base_station)
                drone.status = DroneStatus.SEARCHING
                continue
            if drone.battery < self.dispatch_ready_threshold and drone.location == self.base_station:
                drone.status = DroneStatus.CHARGING
                continue

            sector_start, sector_end = self._sector_bounds(idx, len(drone_ids), self.width)
            current = drone.location
            base = self.base_station
            sector_candidates: list[GridPoint] = []
            global_candidates: list[GridPoint] = []
            for x in range(self.width):
                for y in range(self.height):
                    point = (x, y)
                    if point in self.searched_cells:
                        continue
                    travel = self._distance(current, point)
                    ret = self._distance(point, base)
                    # Preserve strict return reserve.
                    if int(drone.battery) <= (travel + ret):
                        continue
                    if sector_start <= x < sector_end:
                        sector_candidates.append(point)
                    else:
                        global_candidates.append(point)

            candidates = sector_candidates or global_candidates
            if not candidates:
                self._model.set_waypoint(drone_id, base)
                drone.status = DroneStatus.SEARCHING
                continue
            candidates.sort(key=lambda p: (self._distance(current, p), self._distance(p, base), p[1], p[0]))
            target = candidates[0]
            self._model.set_waypoint(drone_id, target)
            drone.status = DroneStatus.SEARCHING

    def _edge_tick(self) -> None:
        now = time.monotonic()
        if now - self._last_edge_tick_ts < max(0.01, float(self.edge_tick_interval_sec)):
            return
        self._last_edge_tick_ts = now
        self._service_charging()
        self._apply_completion_recall_policy()
        self._model.step()

    def _apply_completion_recall_policy(self) -> None:
        total_cells = self.width * self.height
        coverage_ratio = len(self.searched_cells) / total_cells if total_cells else 0.0
        all_survivors_found = len(self.found_survivors) >= len(self.survivors)
        if coverage_ratio < 1.0 and not all_survivors_found:
            return
        for drone in self.drones.values():
            if not drone.is_online():
                continue
            if drone.location == self.base_station:
                if drone.battery < self.dispatch_ready_threshold:
                    drone.status = DroneStatus.CHARGING
                else:
                    drone.status = DroneStatus.IDLE
                continue
            self._model.set_waypoint(drone.drone_id, self.base_station)
            drone.status = DroneStatus.SEARCHING

    def _mark_searched(self, point: GridPoint) -> None:
        self.searched_cells.add((int(point[0]), int(point[1])))
        if (int(point[0]), int(point[1])) in self.survivors:
            self.found_survivors.add((int(point[0]), int(point[1])))

    def get_active_fleet(self) -> list[dict]:
        self._edge_tick()
        return [d.to_public_dict() for d in self.drones.values() if d.is_online()]

    def get_battery_status(self, drone_id: str) -> dict:
        self._edge_tick()
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
            return f"{drone_id} is offline and cannot accept a waypoint."
        if drone.battery <= 0:
            drone.status = DroneStatus.CHARGING
            return f"{drone_id} has no battery and must charge."
        if (
            drone.location == self.base_station
            and (target_x, target_y) != self.base_station
            and drone.battery < self.dispatch_ready_threshold
        ):
            drone.status = DroneStatus.CHARGING
            return (
                f"{drone_id} is still charging at base "
                f"(battery={drone.battery}%, launch_ready={self.dispatch_ready_threshold}%)."
            )

        current_waypoint = self._model.drone_agents[drone_id].waypoint()
        if current_waypoint == (target_x, target_y):
            return (
                f"{drone_id} is already executing waypoint [{target_x}, {target_y}]. "
                "Edge agent continues decentralized path execution."
            )
        if current_waypoint is not None and drone.location != current_waypoint:
            return (
                f"{drone_id} rejected reassignment to [{target_x}, {target_y}] while en route "
                f"to [{current_waypoint[0]}, {current_waypoint[1]}]."
            )

        # Reject unsafe waypoint assignments that cannot preserve return reserve.
        distance_to_target = abs(drone.location[0] - target_x) + abs(drone.location[1] - target_y)
        distance_target_to_base = abs(target_x - self.base_station[0]) + abs(target_y - self.base_station[1])
        required_min_battery = distance_to_target + distance_target_to_base
        if drone.battery < required_min_battery:
            return (
                f"{drone_id} rejected waypoint [{target_x}, {target_y}] due to reserve policy "
                f"(battery={drone.battery}%, required={required_min_battery}%)."
            )

        self._model.set_waypoint(drone_id, (target_x, target_y))
        # Waypoint assignment means the edge drone should be moving unless already offline.
        if drone.location != self.base_station or drone.battery >= self.dispatch_ready_threshold:
            drone.status = DroneStatus.SEARCHING
        return (
            f"{drone_id} accepted waypoint [{target_x}, {target_y}]. "
            "Edge agent will negotiate pathing and move autonomously."
        )

    def scan_sector(self, drone_id: str) -> str:
        drone = self._assert_known_drone(drone_id)
        if not drone.is_online():
            return f"{drone_id} is offline and cannot scan."
        # Thermal sensing is always on; explicit scan call reports current passive result.
        self._mark_searched(drone.location)
        if drone.location in self.survivors:
            return "Scan complete. 1 thermal signature detected!"
        return "Scan complete. No signatures."

    def recall_drone(self, drone_id: str) -> str:
        drone = self._assert_known_drone(drone_id)
        if not drone.is_online():
            return f"{drone_id} is offline and cannot be recalled."
        return self.move_drone(drone_id, self.base_station[0], self.base_station[1])

    def get_mission_status(self) -> dict:
        self._edge_tick()
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
            "total_survivors": len(self.survivors),
            "all_survivors_found": len(self.found_survivors) >= len(self.survivors),
            "found_survivor_positions": self._serialize_points(self.found_survivors),
            "active_drones": len([d for d in self.drones.values() if d.is_online()]),
            "offline_drones": len(offline_ids),
            "offline_drone_ids": offline_ids,
            "total_drones": len(self.drones),
        }
