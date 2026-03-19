## Scenario
1. When the drone's battery is less than 15%, it should return to base [0,0] and recharge immediately.
2. When the drone's battery is less than 30%, it should be assigned to search nearby the base to make sure it can return to base.
3. When the drone's battery is more than 30%, it should be assigned to search the area that is far from the base.
4. Press '1','2','3','4' to mock the drone is dead and unavailable.
5. when one of the drone is unavailable, the system should reassign the task to the other available drones and redesign the drone search pattern.
6. the <thinking> box should show the chain of thought of the agent only.
7. When thermal_scan detects a survivor, the agent must immediately log the exact [x, y] coordinates of the survivor in the <thinking> box and continue the search.
8. when all the survivors are found, all the drones should return to base [0,0] and the mission should end.
