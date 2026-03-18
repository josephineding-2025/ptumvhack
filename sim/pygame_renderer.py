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
        state_lock: Any | None = None,
    ) -> None:
        self.env = env
        self.cell_size = cell_size
        self.panel_width = panel_width
        self.log_provider = log_provider
        self.status_provider = status_provider
        self.fleet_provider = fleet_provider
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

        status_color = {
            "IDLE": (80, 160, 240),
            "SEARCHING": (80, 220, 120),
            "CHARGING": (255, 190, 40),
            "OFFLINE": (200, 70, 70),
        }

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_k and self.fleet_provider is None:
                    # Demo shortcut: mark the first online drone offline.
                    with self.state_lock or nullcontext():
                        fleet = self.env.get_active_fleet()
                        if fleet:
                            self.env.set_offline(fleet[0]["id"])

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
                    status = str(drone.get("status", "IDLE"))
                    location = drone.get("location", [0, 0])
                else:
                    status = drone.status.value
                    location = drone.location
                color = status_color.get(status, (220, 220, 220))
                px = int(location[0]) * self.cell_size + self.cell_size // 2
                py = int(location[1]) * self.cell_size + self.cell_size // 2
                pygame.draw.circle(screen, color, (px, py), self.cell_size // 3)

            panel_x = grid_w
            pygame.draw.rect(screen, (21, 24, 32), pygame.Rect(panel_x, 0, self.panel_width, grid_h))
            pygame.draw.line(screen, (55, 60, 74), (panel_x, 0), (panel_x, grid_h), 2)

            title = font.render("Agent Thinking", True, (230, 236, 245))
            screen.blit(title, (panel_x + 14, 12))
            hint_text = (
                "Press K: force one drone offline"
                if self.fleet_provider is None
                else "MCP view: actions/state come from bridge"
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
            max_lines = max(1, visible_height // 18)
            flat_lines: list[str] = []
            for entry in logs[-60:]:
                for wrapped in self._wrap_text(str(entry), max_chars=46):
                    flat_lines.append(wrapped)
            for line in flat_lines[-max_lines:]:
                screen.blit(small_font.render(line, True, (220, 224, 232)), (panel_x + 14, y))
                y += 18

            pygame.display.flip()
            clock.tick(30)

        pygame.quit()
