import collections


def solve(grid, start, goal):
    directions = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), 
                  (0, 0, 1), (0, 0, -1)]
    
    queue = collections.deque([(start[0], start[1], start[2])])
    visited = set()
    visited.add(start)
    
    while queue:
        x, y, z = queue.popleft()
        
        if (x, y, z) == goal:
            return len(visited) - 1
        
        for dx, dy, dz in directions:
            nx, ny, nz = x + dx, y + dy, z + dz
            
            if not (0 <= nx < 20 and 0 <= ny < 20 and 0 <= nz < 20):
                continue
            if grid[nx][ny][nz] == -1:
                continue
            
            if (nx, ny, nz) not in visited:
                visited.add((nx, ny, nz))
                queue.append((nx, ny, nz))
    
    return -1

