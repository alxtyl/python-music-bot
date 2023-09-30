import os

async def update_queue_file(queue):
    """Atomically update a status file containing the titles
    and durations of songs in the queue.

    Args:
        queue - The wavelink queue.
    """
    temp_queue = queue.copy()
    with open('.queue.txt', 'w') as file:
        for _ in range(temp_queue.count):
            entry = temp_queue.get()
            file.write(f'{entry.title}\n{int(entry.duration)}\n')
    
    # Move to primary file after writing to make atomic
    os.replace('.queue.txt', 'queue.txt')
