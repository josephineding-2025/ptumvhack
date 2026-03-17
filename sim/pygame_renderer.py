from sim.environment import SimulationEnvironment


class PygameRenderer:
    def __init__(self, env: SimulationEnvironment, cell_size: int = 30) -> None:
        self.env = env
        self.cell_size = cell_size

    def run(self) -> None:
        # TODO(Member 2): Implement PyGame render loop.
        # Requirements from spec:
        # - draw grid
        # - render drones by status
        # - support "kill drone" shortcut for self-healing demo
        raise NotImplementedError("PyGame renderer scaffold only.")
