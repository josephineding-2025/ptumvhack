import math
import os
import time
from collections import deque
from contextlib import nullcontext
from typing import Any, Callable

from sim.environment import SimulationEnvironment


class PygameRenderer:
    def __init__(
        self,
        env: SimulationEnvironment,
        cell_size: int = 30,
        panel_width: int = 280,
        log_provider: Callable[[], list[str]] | None = None,
        status_provider: Callable[[], dict[str, Any]] | None = None,
        fleet_provider: Callable[[], list[dict[str, Any]]] | None = None,
        command_submitter: Callable[[str], None] | None = None,
        offline_submitter: Callable[[str], None] | None = None,
        completion_provider: Callable[[], dict[str, Any]] | None = None,
        state_lock: Any | None = None,
    ) -> None:
        self.env = env
        self.cell_size = cell_size
        self.panel_width = panel_width
        self.log_provider = log_provider
        self.status_provider = status_provider
        self.fleet_provider = fleet_provider
        self.command_submitter = command_submitter
        self.offline_submitter = offline_submitter
        self.completion_provider = completion_provider
        self.state_lock = state_lock
        self._render_positions: dict[str, tuple[float, float]] = {}
        self._motion_trails: dict[str, deque[tuple[float, float]]] = {}
        self._flash_until: dict[str, float] = {}
        self._seen_survivors: set[tuple[int, int]] = set()
        self._river_cells = self._build_river_cells()
        self._tree_cells = set(self.env.tree_cells)
        self._mission_popup_open = True

    @staticmethod
    def _safe_call(fn: Callable[[], Any] | None, fallback: object) -> object:
        if fn is None:
            return fallback
        try:
            return fn()
        except Exception:
            return fallback

    @staticmethod
    def _wrap_text(text: str, max_chars: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def _extract_thinking(entry: str) -> str | None:
        start_tag = "<thinking>"
        end_tag = "</thinking>"
        start = entry.find(start_tag)
        end = entry.find(end_tag)
        if start == -1 or end == -1 or end <= start:
            return None
        return entry[start + len(start_tag):end].strip()

    def _cell_center(self, x: int, y: int) -> tuple[float, float]:
        return (
            x * self.cell_size + self.cell_size / 2,
            y * self.cell_size + self.cell_size / 2,
        )

    def _build_river_cells(self) -> set[tuple[int, int]]:
        river: set[tuple[int, int]] = set()
        for y in range(self.env.height):
            center = int(round(4 + 0.22 * y + 1.3 * math.sin(y * 0.55)))
            for dx in (-1, 0, 1):
                x = center + dx
                if 0 <= x < self.env.width:
                    river.add((x, y))
        return river

    def _push_trail_point(self, drone_id: str, point: tuple[float, float]) -> None:
        trail = self._motion_trails.setdefault(drone_id, deque(maxlen=18))
        if not trail:
            trail.append(point)
            return
        last = trail[-1]
        if abs(last[0] - point[0]) + abs(last[1] - point[1]) >= max(1.5, self.cell_size * 0.18):
            trail.append(point)

    @staticmethod
    def _read_text_file_tail(path: str, max_lines: int = 18) -> list[str]:
        try:
            with open(path, encoding="utf-8") as handle:
                lines = [line.rstrip("\n") for line in handle.readlines()]
        except OSError:
            return []
        return lines[-max_lines:]

    @staticmethod
    def _drone_payload(drone: Any) -> dict[str, Any]:
        if isinstance(drone, dict):
            return {
                "id": str(drone.get("id", "DR-??")),
                "status": str(drone.get("status", "IDLE")),
                "location": drone.get("location", [0, 0]),
                "battery": int(drone.get("battery", 0)),
                "waypoint": drone.get("waypoint"),
                "last_move_tick": drone.get("last_move_tick"),
            }
        return {
            "id": drone.drone_id,
            "status": drone.status.value,
            "location": [int(drone.location[0]), int(drone.location[1])],
            "battery": int(drone.battery),
            "waypoint": drone.metadata.get("waypoint"),
            "last_move_tick": drone.metadata.get("last_move_tick"),
        }

    def _update_detection_flashes(
        self,
        drones: list[dict[str, Any]],
        found_survivor_positions: set[tuple[int, int]],
        now: float,
    ) -> None:
        new_hits = found_survivor_positions - self._seen_survivors
        if not new_hits:
            return
        for found in new_hits:
            for drone in drones:
                location = drone.get("location", [0, 0])
                if isinstance(location, list) and len(location) == 2:
                    if (int(location[0]), int(location[1])) == found:
                        self._flash_until[str(drone.get("id", "DR-??"))] = now + 1.2
        self._seen_survivors = set(found_survivor_positions)

    def run(self) -> None:
        try:
            import pygame
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pygame is not installed. Run setup first.") from exc

        pygame.init()
        grid_w = self.env.width * self.cell_size
        grid_h = self.env.height * self.cell_size
        screen = pygame.display.set_mode((grid_w + self.panel_width, grid_h))
        pygame.display.set_caption("Aegis Swarm Simulation")
        clock = pygame.time.Clock()
        title_font = pygame.font.SysFont("bahnschrift", 22, bold=True)
        small_font = pygame.font.SysFont("consolas", 14)
        tiny_font = pygame.font.SysFont("consolas", 12)

        status_color = {
            "IDLE": (124, 232, 255),
            "SEARCHING": (72, 255, 232),
            "CHARGING": (176, 188, 198),
            "OFFLINE": (108, 118, 128),
        }

        running = True
        input_text = ""
        last_submitted = ""
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                    self._mission_popup_open = not self._mission_popup_open
                if event.type == pygame.KEYDOWN:
                    key_to_drone = {
                        pygame.K_1: "DR-01",
                        pygame.K_2: "DR-02",
                        pygame.K_3: "DR-03",
                        pygame.K_4: "DR-04",
                    }
                    drone_id = key_to_drone.get(event.key)
                    if drone_id:
                        if self.offline_submitter is not None:
                            self.offline_submitter(drone_id)
                        else:
                            with self.state_lock or nullcontext():
                                if drone_id in self.env.drones:
                                    self.env.set_offline(drone_id)
                if event.type == pygame.KEYDOWN and self.command_submitter is not None:
                    if last_submitted:
                        continue
                    if event.key == pygame.K_RETURN:
                        message = input_text.strip()
                        if message:
                            self.command_submitter(message)
                            last_submitted = message
                            input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        input_text = ""
                    else:
                        if event.unicode and event.unicode.isprintable():
                            input_text += event.unicode

            now = time.perf_counter()
            pulse = 0.5 + 0.5 * math.sin(now * 3.6)

            if self.status_provider is not None:
                mission_status_raw = self._safe_call(self.status_provider, {})
            else:
                mission_status_raw = self.env.get_mission_status()
            mission_status = mission_status_raw if isinstance(mission_status_raw, dict) else {}
            searched_positions = {
                (int(point[0]), int(point[1]))
                for point in mission_status.get("searched_positions", [])
                if isinstance(point, (list, tuple)) and len(point) == 2
            }
            found_survivor_positions = {
                (int(point[0]), int(point[1]))
                for point in mission_status.get("found_survivor_positions", [])
                if isinstance(point, (list, tuple)) and len(point) == 2
            }

            if self.fleet_provider is not None:
                drone_items = self._safe_call(self.fleet_provider, [])
                drones_raw = drone_items if isinstance(drone_items, list) else []
            else:
                with self.state_lock or nullcontext():
                    drones_raw = list(self.env.drones.values())
            drones = [self._drone_payload(drone) for drone in drones_raw]
            self._update_detection_flashes(drones, found_survivor_positions, now)

            screen.fill((4, 12, 10))
            grid_surface = pygame.Surface((grid_w, grid_h), pygame.SRCALPHA)
            trail_surface = pygame.Surface((grid_w, grid_h), pygame.SRCALPHA)
            drone_surface = pygame.Surface((grid_w, grid_h), pygame.SRCALPHA)
            overlay_surface = pygame.Surface((grid_w, grid_h), pygame.SRCALPHA)

            for y in range(grid_h):
                shade = int(8 + 18 * (y / max(1, grid_h)))
                pygame.draw.line(screen, (4, 18 + shade, 14 + shade), (0, y), (grid_w, y))

            radar_center = (grid_w // 2, grid_h // 2)
            for radius in range(self.cell_size * 2, max(grid_w, grid_h), self.cell_size * 3):
                alpha = max(12, 70 - radius // 10)
                pygame.draw.circle(grid_surface, (50, 255, 190, alpha), radar_center, radius, width=1)

            for x in range(self.env.width):
                for y in range(self.env.height):
                    rect = pygame.Rect(
                        x * self.cell_size,
                        y * self.cell_size,
                        self.cell_size,
                        self.cell_size,
                    )
                    muddy = (74, 56, 32, 236) if (x + y) % 2 == 0 else (92, 68, 38, 228)
                    pygame.draw.rect(grid_surface, muddy, rect)
                    if (x, y) in self._river_cells:
                        river_color = (26, 118, 220, 225) if (x + y) % 2 == 0 else (52, 154, 255, 220)
                        pygame.draw.rect(grid_surface, river_color, rect)
                        pygame.draw.line(
                            grid_surface,
                            (162, 232, 255, 120),
                            (rect.x + 3, rect.y + rect.height // 3),
                            (rect.right - 3, rect.y + rect.height // 3),
                            width=1,
                        )
                    elif (x, y) in self._tree_cells:
                        trunk_x = rect.x + rect.width // 2
                        pygame.draw.line(
                            grid_surface,
                            (88, 56, 26, 220),
                            (trunk_x, rect.y + rect.height - 5),
                            (trunk_x, rect.y + rect.height // 2 + 2),
                            width=max(1, self.cell_size // 10),
                        )
                        pygame.draw.circle(
                            grid_surface,
                            (24, 164, 84, 220),
                            (trunk_x, rect.y + rect.height // 2),
                            max(4, self.cell_size // 4),
                        )
                        pygame.draw.circle(
                            grid_surface,
                            (84, 220, 124, 120),
                            (trunk_x - 2, rect.y + rect.height // 2 - 2),
                            max(3, self.cell_size // 5),
                        )

            for x, y in searched_positions:
                rect = pygame.Rect(
                    x * self.cell_size + 1,
                    y * self.cell_size + 1,
                    self.cell_size - 2,
                    self.cell_size - 2,
                )
                alpha = 60 if (x, y) not in found_survivor_positions else 142
                color = (70, 255, 210, alpha) if (x, y) not in found_survivor_positions else (255, 92, 92, alpha)
                pygame.draw.rect(grid_surface, color, rect, border_radius=max(2, self.cell_size // 7))

            base_rect = pygame.Rect(
                self.env.base_station[0] * self.cell_size + 2,
                self.env.base_station[1] * self.cell_size + 2,
                self.cell_size - 4,
                self.cell_size - 4,
            )
            pygame.draw.rect(grid_surface, (178, 244, 255, 220), base_rect, border_radius=max(4, self.cell_size // 6))
            pygame.draw.rect(grid_surface, (72, 240, 255, 240), base_rect, 2, border_radius=max(4, self.cell_size // 6))

            for x in range(self.env.width):
                for y in range(self.env.height):
                    rect = pygame.Rect(
                        x * self.cell_size,
                        y * self.cell_size,
                        self.cell_size,
                        self.cell_size,
                    )
                    pygame.draw.rect(grid_surface, (46, 255, 198, 48), rect, width=1)

            for survivor in self.env.survivors:
                sx, sy = self._cell_center(survivor[0], survivor[1])
                pygame.draw.circle(grid_surface, (255, 84, 84, 220), (int(sx), int(sy)), max(4, self.cell_size // 6))
                pygame.draw.circle(grid_surface, (255, 210, 210, 100), (int(sx), int(sy)), max(6, self.cell_size // 4), width=1)

            for survivor in found_survivor_positions:
                sx, sy = self._cell_center(survivor[0], survivor[1])
                ring_radius = int(self.cell_size * (0.28 + 0.14 * pulse))
                pygame.draw.circle(grid_surface, (255, 120, 120, 110), (int(sx), int(sy)), ring_radius + 8, width=2)
                pygame.draw.circle(grid_surface, (255, 214, 120, 170), (int(sx), int(sy)), max(4, self.cell_size // 7))

            for drone in drones:
                drone_id = drone["id"]
                status = drone["status"]
                location = drone["location"]
                if not isinstance(location, list) or len(location) != 2:
                    continue
                tx, ty = self._cell_center(int(location[0]), int(location[1]))
                current_pos = self._render_positions.get(drone_id, (tx, ty))
                smoothing = 0.24 if status != "OFFLINE" else 0.16
                next_pos = (
                    current_pos[0] + (tx - current_pos[0]) * smoothing,
                    current_pos[1] + (ty - current_pos[1]) * smoothing,
                )
                self._render_positions[drone_id] = next_pos
                self._push_trail_point(drone_id, next_pos)

                waypoint = drone.get("waypoint")
                if isinstance(waypoint, (list, tuple)) and len(waypoint) == 2:
                    wx, wy = self._cell_center(int(waypoint[0]), int(waypoint[1]))
                    pygame.draw.line(
                        trail_surface,
                        (120, 138, 180, 52),
                        (int(next_pos[0]), int(next_pos[1])),
                        (int(wx), int(wy)),
                        width=1,
                    )

                trail = list(self._motion_trails.get(drone_id, ()))
                if len(trail) >= 2:
                    for index in range(1, len(trail)):
                        fade = int(78 * index / len(trail))
                        pygame.draw.line(
                            trail_surface,
                            (*status_color.get(status, (220, 220, 220)), fade),
                            (int(trail[index - 1][0]), int(trail[index - 1][1])),
                            (int(trail[index][0]), int(trail[index][1])),
                            width=max(2, self.cell_size // 9),
                        )

                color = status_color.get(status, (220, 220, 220))
                radius = max(5, self.cell_size // 3)
                glow_radius = radius + max(6, self.cell_size // 4)
                pygame.draw.circle(
                    drone_surface,
                    (*color, 55),
                    (int(next_pos[0]), int(next_pos[1])),
                    glow_radius,
                )
                pygame.draw.circle(
                    drone_surface,
                    (*color, 220),
                    (int(next_pos[0]), int(next_pos[1])),
                    radius,
                )
                pygame.draw.circle(
                    drone_surface,
                    (245, 248, 255, 235),
                    (int(next_pos[0] - radius * 0.35), int(next_pos[1] - radius * 0.35)),
                    max(2, radius // 3),
                )

                if now < self._flash_until.get(drone_id, 0.0):
                    flash_pulse = 0.55 + 0.45 * math.sin(now * 18)
                    flash_radius = radius + int(self.cell_size * (0.3 + 0.12 * flash_pulse))
                    pygame.draw.circle(
                        drone_surface,
                        (255, 244, 186, 190),
                        (int(next_pos[0]), int(next_pos[1])),
                        flash_radius,
                        width=3,
                    )
                    pygame.draw.circle(
                        drone_surface,
                        (255, 116, 116, 120),
                        (int(next_pos[0]), int(next_pos[1])),
                        flash_radius + 8,
                        width=2,
                    )

                battery = int(drone.get("battery", 0))
                card_w = max(86, self.cell_size * 3 + 10)
                card_h = 28
                pref_x = int(next_pos[0]) + self.cell_size // 2 + 4
                card_x = pref_x if pref_x + card_w < grid_w - 4 else int(next_pos[0]) - card_w - self.cell_size // 2 - 4
                card_y = max(4, min(grid_h - card_h - 4, int(next_pos[1]) - card_h // 2))
                anchor_y = int(next_pos[1])
                attach_x = card_x if card_x > int(next_pos[0]) else card_x + card_w
                pygame.draw.line(
                    overlay_surface,
                    (72, 240, 255, 175),
                    (int(next_pos[0]), anchor_y),
                    (attach_x, anchor_y),
                    width=1,
                )
                pygame.draw.rect(
                    overlay_surface,
                    (4, 18, 18, 228),
                    pygame.Rect(card_x, card_y, card_w, card_h),
                    border_radius=6,
                )
                pygame.draw.rect(
                    overlay_surface,
                    (*color, 235),
                    pygame.Rect(card_x, card_y, card_w, card_h),
                    width=1,
                    border_radius=6,
                )
                id_surface = tiny_font.render(drone_id, True, (220, 255, 245))
                status_surface = tiny_font.render(status, True, (190, 244, 218) if status != "OFFLINE" else (255, 176, 176))
                overlay_surface.blit(id_surface, (card_x + 6, card_y + 4))
                overlay_surface.blit(status_surface, (card_x + 6, card_y + 14))
                bar_x = card_x + card_w - 34
                bar_y = card_y + 7
                bar_rect = pygame.Rect(bar_x, bar_y, 24, 12)
                pygame.draw.rect(overlay_surface, (16, 28, 26, 240), bar_rect, border_radius=3)
                fill_w = max(2, int((max(0, min(100, battery)) / 100) * (bar_rect.width - 2))) if battery > 0 else 0
                if fill_w > 0:
                    bar_color = (80, 255, 180, 235) if battery >= 50 else (255, 208, 80, 235) if battery >= 25 else (255, 86, 86, 235)
                    pygame.draw.rect(
                        overlay_surface,
                        bar_color,
                        pygame.Rect(bar_rect.x + 1, bar_rect.y + 1, fill_w, bar_rect.height - 2),
                        border_radius=2,
                    )
                pygame.draw.rect(overlay_surface, (188, 244, 240, 220), bar_rect, 1, border_radius=3)

            screen.blit(grid_surface, (0, 0))
            screen.blit(trail_surface, (0, 0))
            screen.blit(drone_surface, (0, 0))
            screen.blit(overlay_surface, (0, 0))

            panel_x = grid_w
            panel_rect = pygame.Rect(panel_x, 0, self.panel_width, grid_h)
            pygame.draw.rect(screen, (2, 10, 10), panel_rect)
            pygame.draw.line(screen, (72, 240, 255), (panel_x, 0), (panel_x, grid_h), 2)
            inner_rect = pygame.Rect(panel_x + 10, 10, self.panel_width - 20, grid_h - 20)
            pygame.draw.rect(screen, (4, 16, 16), inner_rect, border_radius=12)
            pygame.draw.rect(screen, (70, 255, 210), inner_rect, 1, border_radius=12)

            title = title_font.render("THINKING", True, (204, 255, 242))
            screen.blit(title, (panel_x + 18, 18))
            pygame.draw.line(screen, (60, 220, 190), (panel_x + 18, 50), (panel_x + self.panel_width - 18, 50), 1)

            raw_logs = self._safe_call(self.log_provider, [])
            logs = raw_logs if isinstance(raw_logs, list) else []
            completion_state_raw = self._safe_call(self.completion_provider, {})
            completion_state = completion_state_raw if isinstance(completion_state_raw, dict) else {}
            mission_complete = bool(completion_state.get("mission_complete", False))
            exported_log_path = str(completion_state.get("exported_log_path", "") or "")

            input_area_h = 84 if self.command_submitter is not None else 0
            visible_height = grid_h - 62 - 24 - input_area_h
            max_lines = max(1, visible_height // 18)
            flat_lines: list[str] = []
            for entry in logs[-120:]:
                thinking = self._extract_thinking(str(entry))
                if thinking is None:
                    continue
                for wrapped in self._wrap_text(thinking, max_chars=30):
                    flat_lines.append(wrapped)

            y = 62
            for line in flat_lines[-max_lines:]:
                screen.blit(small_font.render(line, True, (172, 255, 224)), (panel_x + 18, y))
                y += 18

            first_command_sent = bool(last_submitted.strip())
            if self.command_submitter is not None:
                input_top = grid_h - 78
                pygame.draw.line(
                    screen,
                    (60, 220, 190),
                    (panel_x + 18, input_top - 10),
                    (panel_x + self.panel_width - 18, input_top - 10),
                    1,
                )
                prompt_text = "First command to central agent"
                if first_command_sent:
                    prompt_text = "Initial command locked"
                prompt = small_font.render(prompt_text, True, (198, 255, 232))
                screen.blit(prompt, (panel_x + 18, input_top))
                input_rect = pygame.Rect(panel_x + 18, input_top + 24, self.panel_width - 36, 28)
                fill_color = (6, 20, 20) if not first_command_sent else (10, 18, 18)
                border_color = (88, 255, 220) if not first_command_sent else (96, 132, 128)
                pygame.draw.rect(screen, fill_color, input_rect, border_radius=8)
                pygame.draw.rect(screen, border_color, input_rect, 1, border_radius=8)
                shown = input_text[-28:] if not first_command_sent else last_submitted[-28:]
                text_color = (232, 255, 244) if not first_command_sent else (176, 214, 208)
                text_surface = small_font.render(shown, True, text_color)
                screen.blit(text_surface, (input_rect.x + 8, input_rect.y + 6))
                helper = "Press Enter to dispatch" if not first_command_sent else "Central agent already tasked"
                screen.blit(small_font.render(helper, True, (132, 208, 192)), (panel_x + 18, input_top + 58))

            if mission_complete and self._mission_popup_open:
                popup_surface = pygame.Surface((grid_w + self.panel_width, grid_h), pygame.SRCALPHA)
                popup_surface.fill((2, 8, 8, 176))
                screen.blit(popup_surface, (0, 0))
                popup_w = min(grid_w + self.panel_width - 80, 700)
                popup_h = min(grid_h - 60, 520)
                popup_x = (grid_w + self.panel_width - popup_w) // 2
                popup_y = (grid_h - popup_h) // 2
                popup_rect = pygame.Rect(popup_x, popup_y, popup_w, popup_h)
                pygame.draw.rect(screen, (6, 18, 18), popup_rect, border_radius=14)
                pygame.draw.rect(screen, (88, 255, 220), popup_rect, 2, border_radius=14)
                title = title_font.render("MISSION LOG", True, (220, 255, 245))
                screen.blit(title, (popup_x + 18, popup_y + 16))
                hint = small_font.render("Press M to close", True, (160, 220, 208))
                screen.blit(hint, (popup_x + popup_w - 138, popup_y + 22))
                pygame.draw.line(screen, (70, 255, 210), (popup_x + 18, popup_y + 50), (popup_x + popup_w - 18, popup_y + 50), 1)

                mission_lines: list[str] = []
                if exported_log_path and os.path.exists(exported_log_path):
                    mission_lines = self._read_text_file_tail(exported_log_path, max_lines=22)
                if not mission_lines:
                    for entry in logs[-22:]:
                        text = str(entry)
                        if text.startswith("<thinking>"):
                            extracted = self._extract_thinking(text)
                            text = extracted if extracted is not None else text
                        mission_lines.append(text)

                y = popup_y + 62
                max_width_chars = max(24, (popup_w - 36) // 9)
                for raw_line in mission_lines:
                    line = raw_line if raw_line.strip() else " "
                    for wrapped in self._wrap_text(line, max_chars=max_width_chars):
                        if y > popup_y + popup_h - 26:
                            break
                        screen.blit(small_font.render(wrapped, True, (188, 255, 228)), (popup_x + 18, y))
                        y += 18

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()
