from collections import deque


def solve(grid, start, goal):
    """Solve shortest path in 3D grid using BFS."""
    
    if start == goal:
        return 0
    
    # Directions: x, y, z axes (6 directions)
    directions = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), 
                  (0, 0, 1), (0, 0, -1)]
    
    # BFS initialization
    queue = deque([(start[0], start[1], start[2], 0)])  # x, y, z, distance
    visited = set()
    visited.add(start)
    
    while queue:
        x, y, z, dist = queue.popleft()
        
        for dx, dy, dz in directions:
            nx, ny, nz = x + dx, y + dy, z + dz
            
            # Check bounds and obstacles
            if not (0 <= nx < 7 and 0 <= ny < 7 and 0 <= nz < 7):
                continue
            if grid[nx][ny][nz] == -1:
                continue
            
            if (nx, ny, nz) in visited:
                continue
            
            # Check if goal reached
            if (nx, ny, nz) == goal:
                return dist + 1
            
            visited.add((nx, ny, nz))
            queue.append((nx, ny, nz, dist + 1))
    
    return -1

