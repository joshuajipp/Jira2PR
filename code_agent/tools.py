"""Tool definitions and execution for the Bedrock code agent.

Defines the tools the AI model can call and the executor that runs them
against the local repository.

Tools available:
- list_directory        — list files/dirs at a path
- list_directory_tree   — recursive tree view of the repo
- read_file             — read full file contents
- read_file_lines       — read a specific line range from a file
- write_file            — overwrite an existing file
- create_file           — create a new file (auto-creates parent dirs)
- delete_file           — delete a file
- rename_file           — move or rename a file
- patch_file            — search-and-replace within a file (surgical edit)
- search_in_files       — grep/regex search across the repo
- run_command           — execute a shell command in the repo
"""

import os
import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Tool specifications (Bedrock Converse API format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    # --- Exploration tools ---
    {
        "toolSpec": {
            "name": "list_directory",
            "description": (
                "List files and directories at a given path in the repository. "
                "Returns entries prefixed with [DIR] or [FILE]. Only shows "
                "one level deep."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Relative path within the repo to list. "
                                "Use '.' for the repository root."
                            ),
                        }
                    },
                    "required": ["path"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_directory_tree",
            "description": (
                "Show a recursive tree view of the repository structure. "
                "Useful for quickly understanding the full project layout. "
                "Directories like .git, node_modules, __pycache__ are skipped."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Relative path to start the tree from. "
                                "Use '.' for the repository root."
                            ),
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": (
                                "Maximum depth to recurse. Default is 4. "
                                "Use a smaller number for large repos."
                            ),
                        },
                    },
                    "required": ["path"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_in_files",
            "description": (
                "Search for a text pattern (regex supported) across all files "
                "in the repository or a subdirectory. Returns matching lines "
                "with file paths and line numbers. Extremely useful for finding "
                "where functions, variables, imports, or strings are used."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": (
                                "The text or regex pattern to search for. "
                                "Examples: 'def handle_login', 'import.*React', "
                                "'TODO', 'className=\"btn\"'."
                            ),
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "Relative path to search within. Use '.' to "
                                "search the entire repository. Use a subdirectory "
                                "like 'src/' to narrow the search."
                            ),
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": (
                                "Optional glob to filter file types. "
                                "Examples: '*.py', '*.js', '*.tsx'. "
                                "Leave empty to search all files."
                            ),
                        },
                    },
                    "required": ["pattern", "path"],
                }
            },
        }
    },
    # --- Read tools ---
    {
        "toolSpec": {
            "name": "read_file",
            "description": "Read the full contents of a file in the repository.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the file within the repo.",
                        }
                    },
                    "required": ["path"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "read_file_lines",
            "description": (
                "Read a specific range of lines from a file. Useful for "
                "large files where you only need to see a particular section. "
                "Lines are 1-indexed."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the file.",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "First line to read (1-indexed, inclusive).",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Last line to read (1-indexed, inclusive).",
                        },
                    },
                    "required": ["path", "start_line", "end_line"],
                }
            },
        }
    },
    # --- Write / modify tools ---
    {
        "toolSpec": {
            "name": "write_file",
            "description": (
                "Overwrite an existing file in the repository with new content. "
                "You must provide the complete file content."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the existing file.",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full new content to write to the file.",
                        },
                    },
                    "required": ["path", "content"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_file",
            "description": (
                "Create a new file in the repository. Parent directories will "
                "be created automatically if they do not exist."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path for the new file.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content of the new file.",
                        },
                    },
                    "required": ["path", "content"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "patch_file",
            "description": (
                "Make a surgical edit to a file by replacing a specific text "
                "snippet with new text. This is more efficient than write_file "
                "for small changes to large files because you only need to "
                "specify the part that changes, not rewrite the whole file. "
                "The old_text must match exactly (including whitespace/indentation)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the file to patch.",
                        },
                        "old_text": {
                            "type": "string",
                            "description": (
                                "The exact text to find and replace. Must match "
                                "the file contents exactly, including whitespace "
                                "and indentation."
                            ),
                        },
                        "new_text": {
                            "type": "string",
                            "description": "The text to replace old_text with.",
                        },
                    },
                    "required": ["path", "old_text", "new_text"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "delete_file",
            "description": "Delete a file from the repository.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the file to delete.",
                        }
                    },
                    "required": ["path"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "rename_file",
            "description": (
                "Move or rename a file within the repository. "
                "Parent directories for the new path will be created "
                "automatically if they do not exist."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "old_path": {
                            "type": "string",
                            "description": "Current relative path of the file.",
                        },
                        "new_path": {
                            "type": "string",
                            "description": "New relative path for the file.",
                        },
                    },
                    "required": ["old_path", "new_path"],
                }
            },
        }
    },
    # --- Execution tools ---
    {
        "toolSpec": {
            "name": "run_command",
            "description": (
                "Execute a shell command in the repository directory. "
                "Use this to run tests, install dependencies, build the "
                "project, or check the output of code. "
                "Returns stdout, stderr, and the exit code. "
                "Commands time out after 60 seconds. "
                "IMPORTANT: Only run safe, non-destructive commands. "
                "Do NOT run commands that delete the repo or modify git history."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                "The shell command to run. Examples: "
                                "'npm install', 'python -m pytest', "
                                "'cat package.json', 'ls -la src/'."
                            ),
                        }
                    },
                    "required": ["command"],
                }
            },
        }
    },
]


# ---------------------------------------------------------------------------
# Secure path resolution
# ---------------------------------------------------------------------------

def _resolve_safe_path(repo_path: str, relative_path: str) -> Path:
    """Resolve a relative path within the repo, preventing path traversal.

    Raises ValueError if the resolved path escapes the repo root.
    """
    base = Path(repo_path).resolve()
    target = (base / relative_path).resolve()

    if not str(target).startswith(str(base)):
        raise ValueError(
            f"Path traversal blocked: '{relative_path}' resolves outside the repo."
        )
    return target


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

_WRITE_TOOLS = {"write_file", "create_file", "patch_file", "delete_file", "rename_file"}

def execute_tool(tool_name: str, tool_input: dict, repo_path: str) -> str:
    """Execute a tool call and return the result as a string.

    Parameters
    ----------
    tool_name : str
        Name of the tool to execute.
    tool_input : dict
        The input parameters for the tool (parsed from the model response).
    repo_path : str
        Absolute path to the root of the cloned repository.

    Returns
    -------
    str
        The result of the tool execution (or an error message).
    """
    dispatcher = {
        "list_directory": _exec_list_directory,
        "list_directory_tree": _exec_list_directory_tree,
        "search_in_files": _exec_search_in_files,
        "read_file": _exec_read_file,
        "read_file_lines": _exec_read_file_lines,
        "write_file": _exec_write_file,
        "create_file": _exec_create_file,
        "patch_file": _exec_patch_file,
        "delete_file": _exec_delete_file,
        "rename_file": _exec_rename_file,
        "run_command": _exec_run_command,
    }

    handler = dispatcher.get(tool_name)
    if not handler:
        return f"Error: Unknown tool '{tool_name}'."

    try:
        return handler(tool_input, repo_path)
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error executing {tool_name}: {exc}"


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

IGNORED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".next", ".cache", "dist", "build"}


def _exec_list_directory(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: Directory '{tool_input['path']}' does not exist."
    if not target.is_dir():
        return f"Error: '{tool_input['path']}' is not a directory."

    entries = sorted(target.iterdir())
    lines = []
    for entry in entries:
        if entry.name in IGNORED_DIRS or entry.name.startswith("."):
            continue
        prefix = "[DIR] " if entry.is_dir() else "[FILE]"
        lines.append(f"{prefix} {entry.name}")

    if not lines:
        return "(empty directory)"
    return "\n".join(lines)


def _exec_list_directory_tree(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: Directory '{tool_input['path']}' does not exist."
    if not target.is_dir():
        return f"Error: '{tool_input['path']}' is not a directory."

    max_depth = tool_input.get("max_depth", 4)
    lines = []
    _build_tree(target, "", max_depth, 0, lines)

    if not lines:
        return "(empty directory)"

    # Cap output to prevent massive responses
    if len(lines) > 500:
        lines = lines[:500]
        lines.append(f"... (truncated, {len(lines)}+ entries)")

    return "\n".join(lines)


def _build_tree(
    directory: Path, prefix: str, max_depth: int, current_depth: int, lines: list
) -> None:
    """Recursively build a tree representation."""
    if current_depth >= max_depth:
        return

    entries = sorted(
        [e for e in directory.iterdir()
         if e.name not in IGNORED_DIRS and not e.name.startswith(".")],
        key=lambda e: (not e.is_dir(), e.name),  # dirs first
    )

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _build_tree(entry, prefix + extension, max_depth, current_depth + 1, lines)


def _exec_search_in_files(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: Path '{tool_input['path']}' does not exist."

    pattern = tool_input["pattern"]
    file_pattern = tool_input.get("file_pattern", "")

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Error: Invalid regex pattern: {exc}"

    matches = []
    max_matches = 100  # Cap to prevent massive output

    if target.is_file():
        files_to_search = [target]
    else:
        files_to_search = sorted(target.rglob(file_pattern or "*"))

    for filepath in files_to_search:
        if not filepath.is_file():
            continue

        # Skip ignored dirs
        parts = filepath.relative_to(Path(repo_path).resolve()).parts
        if any(part in IGNORED_DIRS or part.startswith(".") for part in parts):
            continue

        # Skip binary files
        try:
            content = filepath.read_text(errors="replace")
        except Exception:
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                rel_path = filepath.relative_to(Path(repo_path).resolve())
                matches.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                if len(matches) >= max_matches:
                    matches.append(f"... (search capped at {max_matches} results)")
                    return "\n".join(matches)

    if not matches:
        return f"No matches found for pattern '{pattern}'."
    return "\n".join(matches)


def _exec_read_file(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: File '{tool_input['path']}' does not exist."
    if not target.is_file():
        return f"Error: '{tool_input['path']}' is not a file."

    content = target.read_text(errors="replace")
    if not content:
        return "(file is empty)"
    return content


def _exec_read_file_lines(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: File '{tool_input['path']}' does not exist."
    if not target.is_file():
        return f"Error: '{tool_input['path']}' is not a file."

    start = tool_input["start_line"]
    end = tool_input["end_line"]

    if start < 1:
        return "Error: start_line must be >= 1."
    if end < start:
        return "Error: end_line must be >= start_line."

    lines = target.read_text(errors="replace").splitlines()

    if start > len(lines):
        return f"Error: File only has {len(lines)} lines, but start_line is {start}."

    # Clamp end to actual file length
    end = min(end, len(lines))

    selected = lines[start - 1 : end]
    numbered = [f"{i}: {line}" for i, line in enumerate(selected, start)]
    return "\n".join(numbered)


def _exec_write_file(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return (
            f"Error: File '{tool_input['path']}' does not exist. "
            "Use create_file to create new files."
        )
    if not target.is_file():
        return f"Error: '{tool_input['path']}' is not a file."

    target.write_text(tool_input["content"])
    return f"Successfully wrote to {tool_input['path']}"


def _exec_create_file(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if target.exists():
        return (
            f"Error: '{tool_input['path']}' already exists. "
            "Use write_file to overwrite existing files."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tool_input["content"])
    return f"Successfully created {tool_input['path']}"


def _exec_patch_file(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: File '{tool_input['path']}' does not exist."
    if not target.is_file():
        return f"Error: '{tool_input['path']}' is not a file."

    content = target.read_text(errors="replace")
    old_text = tool_input["old_text"]
    new_text = tool_input["new_text"]

    count = content.count(old_text)
    if count == 0:
        return (
            f"Error: old_text not found in '{tool_input['path']}'. "
            "Make sure the text matches exactly, including whitespace and indentation."
        )
    if count > 1:
        return (
            f"Error: old_text found {count} times in '{tool_input['path']}'. "
            "Please provide a more unique snippet to avoid ambiguous replacements."
        )

    new_content = content.replace(old_text, new_text, 1)
    target.write_text(new_content)
    return f"Successfully patched {tool_input['path']}"


def _exec_delete_file(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: File '{tool_input['path']}' does not exist."
    if not target.is_file():
        return f"Error: '{tool_input['path']}' is not a file. Only files can be deleted."

    target.unlink()
    return f"Successfully deleted {tool_input['path']}"


def _exec_rename_file(tool_input: dict, repo_path: str) -> str:
    old_target = _resolve_safe_path(repo_path, tool_input["old_path"])
    new_target = _resolve_safe_path(repo_path, tool_input["new_path"])

    if not old_target.exists():
        return f"Error: '{tool_input['old_path']}' does not exist."
    if not old_target.is_file():
        return f"Error: '{tool_input['old_path']}' is not a file."
    if new_target.exists():
        return f"Error: '{tool_input['new_path']}' already exists."

    new_target.parent.mkdir(parents=True, exist_ok=True)
    old_target.rename(new_target)
    return f"Successfully renamed {tool_input['old_path']} → {tool_input['new_path']}"


# Allowed commands prefix whitelist — block dangerous operations
_BLOCKED_COMMANDS = {"rm -rf /", "rm -rf ~", "git push", "git reset --hard"}


def _exec_run_command(tool_input: dict, repo_path: str) -> str:
    command = tool_input["command"]

    # Basic safety: block obviously dangerous commands
    cmd_lower = command.lower().strip()
    for blocked in _BLOCKED_COMMANDS:
        if cmd_lower.startswith(blocked):
            return f"Error: Command '{command}' is blocked for safety."

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        output_parts.append(f"EXIT CODE: {result.returncode}")

        output = "\n\n".join(output_parts)

        # Cap output length to prevent massive tool results
        if len(output) > 10000:
            output = output[:10000] + "\n... (output truncated at 10000 chars)"

        return output

    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as exc:
        return f"Error running command: {exc}"
