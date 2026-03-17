from sim.environment import SimulationEnvironment


class PygameRenderer:
    def __init__(self, env: SimulationEnvironment, cell_size: int = 30) -> None:
        self.env = env
        self.cell_size = cell_size

    def run(self) -> None:
        try:
            import pygame
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pygame is not installed. Run setup first.") from exc

        pygame.init()
        screen = pygame.display.set_mode((self.env.width * self.cell_size, self.env.height * self.cell_size))
        pygame.display.set_caption("Aegis Swarm Simulation")
        clock = pygame.time.Clock()

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
                if event.type == pygame.KEYDOWN and event.key == pygame.K_k:
                    # Demo shortcut: mark the first online drone offline.
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

            for drone in self.env.drones.values():
                color = status_color.get(drone.status.value, (220, 220, 220))
                px = drone.location[0] * self.cell_size + self.cell_size // 2
                py = drone.location[1] * self.cell_size + self.cell_size // 2
                pygame.draw.circle(screen, color, (px, py), self.cell_size // 3)

            pygame.display.flip()
            clock.tick(30)

        pygame.quit()
