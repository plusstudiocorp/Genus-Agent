"""
bash_tool.py

Persistent terminal management for the assistant, Windows-8.1-safe.

Windows 8.1 doesn't play nicely with PTY libraries (winpty/pywinpty often
fail or behave inconsistently on it), so this uses plain subprocess.Popen
with piped stdin/stdout instead of a real pseudo-terminal. Each terminal
is a long-lived cmd.exe (or custom shell) process the model can keep
writing to and reading from across multiple tool calls.

Terminal IDs are plain integers (1, 2, 3, ...) so the model can refer to
them naturally instead of tracking opaque handles/PIDs.
"""

import subprocess
import threading
import time
import queue

# --- internal state -------------------------------------------------------

_terminals = {}   # id -> _Terminal
_next_id = 1
_lock = threading.Lock()

CREATE_NO_WINDOW = 0x08000000    # fully hidden, no console at all
CREATE_NEW_CONSOLE = 0x00000010  # spawns a real, visible console window


class _Terminal:
    def __init__(self, term_id, command, visible):
        self.id = term_id
        self.visible = visible
        self.output_queue = queue.Queue()
        self.output_log = []

        flags = CREATE_NEW_CONSOLE if visible else CREATE_NO_WINDOW

        self.proc = subprocess.Popen(
            command or "cmd.exe",
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            text=True,
            bufsize=1,
        )

        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()

    def _read_output(self):
        # Blocks on readline() until the process closes stdout (exits).
        try:
            for line in iter(self.proc.stdout.readline, ''):
                self.output_log.append(line)
                self.output_queue.put(line)
        except Exception:
            pass

    def send(self, text):
        if self.proc.poll() is not None:
            return False
        try:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
            return True
        except Exception:
            return False

    def is_alive(self):
        return self.proc.poll() is None

    def get_new_output(self, wait=0.5):
        """Sleep briefly to let the process produce output, then drain the queue."""
        time.sleep(wait)
        lines = []
        while not self.output_queue.empty():
            lines.append(self.output_queue.get())
        return "".join(lines)

    def kill(self):
        try:
            self.proc.kill()
        except Exception:
            pass


# --- tool functions ---------------------------------------------------------

def create_terminal(command: str = "cmd.exe", visible: bool = False) -> str:
    """
    Creates a new persistent terminal session and returns its numeric ID.
    Use this ID with input_terminal / read_terminal / close_terminal.
    Try not to create more then 1 terminal and when created a 3-4 terminals, delete the unused ones.

    Args:
        command: Shell/program to launch (default "cmd.exe"). You can pass
                 something else, e.g. "powershell.exe", to start that instead.
        visible: If True, opens a real, visible console window for this
                 terminal so the user can watch it run. If False (default),
                 the terminal runs completely hidden in the background and
                 does not open any window or interfere with the chat CLI.

    Returns:
        Confirmation string containing the new terminal's numeric ID.
    """
    global _next_id
    print(f"SYS: Creating terminal (visible={visible})...")

    with _lock:
        term_id = _next_id
        _next_id += 1

    try:
        term = _Terminal(term_id, command, visible)
    except Exception as e:
        return f"Error creating terminal: {e}"

    _terminals[term_id] = term
    return f"Terminal {term_id} created."


def input_terminal(terminal_id: int, keys: list[str], wait: float = 0.5) -> str:
    """
    Sends a sequence of inputs to an existing terminal, one at a time, each
    followed by Enter (like typing a command then pressing enter, then
    typing the next one, etc.) Use this both for running commands and for
    answering interactive prompts (y/n, passwords, menu choices...).

    Args:
        terminal_id: Numeric ID returned by create_terminal.
        keys: List of strings, sent in order, one per line
              (e.g. ["dir", "y", "exit"]).
        wait: Seconds to wait after sending all keys before collecting
              output. Increase this for slow commands.

    Returns:
        Newly produced terminal output, or an error message.
    """
    print(f"SYS: Sending input to terminal {terminal_id}...")
    term = _terminals.get(int(terminal_id))

    if term is None:
        return f"Error: Terminal {terminal_id} does not exist."
    if not term.is_alive():
        return f"Error: Terminal {terminal_id} has already exited."

    for key in keys:
        if not term.send(str(key)):
            return f"Error: Failed to send input to terminal {terminal_id} (process may have exited)."

    output = term.get_new_output(wait=wait)
    return output if output else "(no new output yet)"


def read_terminal(terminal_id: int, wait: float = 0.3) -> str:
    """
    Reads any pending output from a terminal without sending new input.
    Useful for checking on a long-running background command.
    """
    term = _terminals.get(int(terminal_id))
    if term is None:
        return f"Error: Terminal {terminal_id} does not exist."
    return term.get_new_output(wait=wait) or "(no new output)"


def list_terminals() -> str:
    """Lists all terminals created so far and whether each is still running."""
    if not _terminals:
        return "No terminals created yet."
    lines = [
        f"{tid}: {'running' if term.is_alive() else 'exited'} (visible={term.visible})"
        for tid, term in _terminals.items()
    ]
    return "\n".join(lines)


def close_terminal(terminal_id: int) -> str:
    """Forcefully kills and removes a terminal."""
    print(f"SYS: Closing terminal {terminal_id}...")
    term = _terminals.pop(int(terminal_id), None)
    if term is None:
        return f"Error: Terminal {terminal_id} does not exist."
    term.kill()
    return f"Terminal {terminal_id} closed."