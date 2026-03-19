from contextlib import nullcontext
from typing import Any, Callable

from sim.environment import SimulationEnvironment


class PygameRenderer:
    def __init__(
        self,
        env: SimulationEnvironment,
        cell_size: int = 30,
        panel_width: int = 420,
        log_provider: Callable[[], list[str]] | None = None,
        status_provider: Callable[[], dict[str, Any]] | None = None,
        fleet_provider: Callable[[], list[dict[str, Any]]] | None = None,
        command_submitter: Callable[[str], None] | None = None,
        offline_submitter: Callable[[str], None] | None = None,
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
        self.state_lock = state_lock

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
        font = pygame.font.SysFont("consolas", 16)
        small_font = pygame.font.SysFont("consolas", 14)
        tiny_font = pygame.font.SysFont("consolas", 12)

        status_color = {
            "IDLE": (80, 160, 240),
            "SEARCHING": (80, 220, 120),
            "CHARGING": (255, 190, 40),
            "OFFLINE": (200, 70, 70),
        }

        running = True
        input_text = ""
        last_submitted = ""
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    # Demo shortcuts: keys 1-4 mark DR-01..DR-04 as offline.
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

            screen.fill((15, 18, 24))
            for x in range(self.env.width):
                for y in range(self.env.height):
                    rect = pygame.Rect(
                        x * self.cell_size,
                        y * self.cell_size,
                        self.cell_size,
                        self.cell_size,
                    )
                    pygame.draw.rect(screen, (35, 40, 55), rect, width=1)

            if self.fleet_provider is not None:
                drone_items = self._safe_call(self.fleet_provider, [])
                drones = drone_items if isinstance(drone_items, list) else []
            else:
                with self.state_lock or nullcontext():
                    drones = list(self.env.drones.values())
            for drone in drones:
                if isinstance(drone, dict):
                    drone_id = str(drone.get("id", "DR-??"))
                    status = str(drone.get("status", "IDLE"))
                    location = drone.get("location", [0, 0])
                    battery = int(drone.get("battery", 0))
                    waypoint = drone.get("waypoint")
                    last_move_tick = drone.get("last_move_tick")
                else:
                    drone_id = drone.drone_id
                    status = drone.status.value
                    location = drone.location
                    battery = int(drone.battery)
                    waypoint = drone.metadata.get("waypoint")
                    last_move_tick = drone.metadata.get("last_move_tick")
                color = status_color.get(status, (220, 220, 220))
                px = int(location[0]) * self.cell_size + self.cell_size // 2
                py = int(location[1]) * self.cell_size + self.cell_size // 2
                pygame.draw.circle(screen, color, (px, py), self.cell_size // 3)
                wait_target = "--"
                if isinstance(waypoint, (list, tuple)) and len(waypoint) == 2:
                    wait_target = f"[{int(waypoint[0])},{int(waypoint[1])}]"
                tick_label = str(int(last_move_tick)) if isinstance(last_move_tick, int) else "-"
                label = (
                    f"{drone_id} {battery}% [{int(location[0])},{int(location[1])}] {status} "
                    f"wait:{wait_target} tick:{tick_label}"
                )
                label_surface = tiny_font.render(label, True, (232, 236, 245))
                lx = min(px + self.cell_size // 3 + 2, grid_w - 220)
                ly = max(2, py - self.cell_size // 2)
                screen.blit(label_surface, (lx, ly))

            panel_x = grid_w
            pygame.draw.rect(screen, (21, 24, 32), pygame.Rect(panel_x, 0, self.panel_width, grid_h))
            pygame.draw.line(screen, (55, 60, 74), (panel_x, 0), (panel_x, grid_h), 2)

            title = font.render("Agent Thinking", True, (230, 236, 245))
            screen.blit(title, (panel_x + 14, 12))
            hint_text = (
                "Press 1/2/3/4: set DR-01..DR-04 offline"
                if self.fleet_provider is None
                else "Press 1/2/3/4 to inject drone failure"
            )
            hint = small_font.render(hint_text, True, (150, 160, 180))
            screen.blit(hint, (panel_x + 14, 34))

            mission_status = self._safe_call(self.status_provider, self.env.get_mission_status())
            status_lines = [
                f"Coverage: {mission_status.get('coverage_ratio', 0) * 100:.1f}%",
                f"Searched Cells: {mission_status.get('searched_cells', 0)}",
                f"Survivors Found: {mission_status.get('survivors_found', 0)}",
                f"Active/Total: {mission_status.get('active_drones', 0)}/{mission_status.get('total_drones', 0)}",
            ]
            y = 62
            for line in status_lines:
                screen.blit(small_font.render(line, True, (195, 205, 225)), (panel_x + 14, y))
                y += 20

            pygame.draw.line(screen, (55, 60, 74), (panel_x + 12, y + 4), (panel_x + self.panel_width - 12, y + 4), 1)
            y += 12

            raw_logs = self._safe_call(self.log_provider, [])
            logs = raw_logs if isinstance(raw_logs, list) else []
            visible_height = grid_h - y - 12
            input_area_h = 80 if self.command_submitter is not None else 0
            visible_height -= input_area_h
            max_lines = max(1, visible_height // 18)
            flat_lines: list[str] = []
            for entry in logs[-60:]:
                thinking = self._extract_thinking(str(entry))
                if thinking is None:
                    continue
                for wrapped in self._wrap_text(thinking, max_chars=46):
                    flat_lines.append(wrapped)
            for line in flat_lines[-max_lines:]:
                screen.blit(small_font.render(line, True, (220, 224, 232)), (panel_x + 14, y))
                y += 18

            if self.command_submitter is not None:
                input_top = grid_h - 74
                pygame.draw.line(
                    screen,
                    (55, 60, 74),
                    (panel_x + 12, input_top - 8),
                    (panel_x + self.panel_width - 12, input_top - 8),
                    1,
                )
                prompt = small_font.render("Command (Enter to send):", True, (195, 205, 225))
                screen.blit(prompt, (panel_x + 14, input_top))
                input_rect = pygame.Rect(panel_x + 14, input_top + 20, self.panel_width - 28, 24)
                pygame.draw.rect(screen, (12, 14, 20), input_rect)
                pygame.draw.rect(screen, (80, 90, 112), input_rect, 1)
                shown = input_text[-52:] if input_text else ""
                text_surface = small_font.render(shown, True, (230, 236, 245))
                screen.blit(text_surface, (input_rect.x + 6, input_rect.y + 4))
                if last_submitted:
                    last_line = f"Last: {last_submitted}"
                    screen.blit(small_font.render(last_line[-52:], True, (150, 160, 180)), (panel_x + 14, input_top + 48))

            pygame.display.flip()
            clock.tick(30)

        pygame.quit()
