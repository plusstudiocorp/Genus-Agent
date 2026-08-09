import json, os

FILE_PATH = "memory.json"


def _load() -> list:
    """Load memory list from disk, creating the file if needed."""
    if not os.path.exists(FILE_PATH) or os.stat(FILE_PATH).st_size == 0:
        return []
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Corrupted or empty file - start fresh instead of crashing
        return []


def _save(memories: list) -> None:
    """Overwrite memory.json with the given list."""
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2)


def store_mem(data: str) -> str:
    """Save a point in the memory."""
    print("SYS: Remembering...")
    memories = _load()
    memories.append(data)
    _save(memories)
    return "Memories Saved Successfully!"


def read_mem() -> str:
    """Reads the whole memory."""
    print("SYS: Recalling...")
    memories = _load()
    if not memories:
        return "You have no memories saved."
    res = "Your memories:\n"
    for i, memory in enumerate(memories):
        res += f"{i + 1}. {memory}\n"
    return res


def remove_mem(line: int) -> str:
    """Removes a point from memory."""
    print("SYS: Forgetting...")
    memories = _load()
    index = line - 1  # user-facing line numbers are 1-indexed (see read_mem)
    if index < 0 or index >= len(memories):
        return f"No memory at line {line}."
    removed = memories.pop(index)
    _save(memories)
    return f"Successfully removed line {line}: {removed}"


def clear_mem() -> str:
    """Clears the whole memory. Use it carefully"""
    print("SYS: Resetting...")
    _save([])
    return "All memories cleared successfully!"

def update_mem(line: int, data: str) -> str:
    """Updates a point and saves it to memory, its a combination of remove and store memory."""
    print("SYS: Revising...")
    memories = _load()
    index = line - 1  # user-facing line numbers are 1-indexed (see read_mem)
    if index < 0 or index >= len(memories):
        return f"No memory at line {line}."
    old = memories[index]
    memories[index] = data
    _save(memories)
    return f"Successfully updated line {line}: '{old}' -> '{data}'"