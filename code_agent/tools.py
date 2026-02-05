"""Tool definitions and execution for the Bedrock code agent.

Defines the tools the AI model can call (list_directory, read_file, write_file,
create_file) and the executor that runs them against the local repository.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Tool specifications (Bedrock Converse API format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "toolSpec": {
            "name": "list_directory",
            "description": (
                "List files and directories at a given path in the repository. "
                "Returns entries prefixed with [DIR] or [FILE]."
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

def execute_tool(tool_name: str, tool_input: dict, repo_path: str) -> str:
    """Execute a tool call and return the result as a string.

    Parameters
    ----------
    tool_name : str
        One of 'list_directory', 'read_file', 'write_file', 'create_file'.
    tool_input : dict
        The input parameters for the tool (parsed from the model response).
    repo_path : str
        Absolute path to the root of the cloned repository.

    Returns
    -------
    str
        The result of the tool execution (or an error message).
    """
    try:
        if tool_name == "list_directory":
            return _exec_list_directory(tool_input, repo_path)
        elif tool_name == "read_file":
            return _exec_read_file(tool_input, repo_path)
        elif tool_name == "write_file":
            return _exec_write_file(tool_input, repo_path)
        elif tool_name == "create_file":
            return _exec_create_file(tool_input, repo_path)
        else:
            return f"Error: Unknown tool '{tool_name}'."
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error executing {tool_name}: {exc}"


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

IGNORED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def _exec_list_directory(tool_input: dict, repo_path: str) -> str:
    target = _resolve_safe_path(repo_path, tool_input["path"])
    if not target.exists():
        return f"Error: Directory '{tool_input['path']}' does not exist."
    if not target.is_dir():
        return f"Error: '{tool_input['path']}' is not a directory."

    entries = sorted(target.iterdir())
    lines = []
    for entry in entries:
        if entry.name in IGNORED_DIRS:
            continue
        prefix = "[DIR] " if entry.is_dir() else "[FILE]"
        lines.append(f"{prefix} {entry.name}")

    if not lines:
        return "(empty directory)"
    return "\n".join(lines)


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

