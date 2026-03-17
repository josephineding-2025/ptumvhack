# Phase 0 Plan (Shared Foundation)

## Objective
Prepare the repository and environment so each member can start their owned implementation files without blocking others.

## Completed
- Created top-level project modules as placeholders:
  - `agent/`, `models/`, `server/`, `sim/`, `presentation/`
- Added foundational repo files:
  - `.gitignore`
  - `requirements.txt`
  - `.env.example`
  - `tools/setup.ps1`
- Updated `README.md` with setup and scope boundaries.

## Remaining in Phase 0 (Shared)
- Verify environment creation and dependency install on a machine with usable Python runtime.
- Lock dependency versions after first successful team integration run.
- Add CI bootstrap workflow (lint + import smoke test) once member files exist.

## Explicitly Out of Scope in This Step
- Member 1/2/3/4 implementation tasks from the spec.
- Feature logic, simulation rendering, MCP tool implementations, and agent orchestration code.
