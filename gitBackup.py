import subprocess
from typing import Optional

class GitCommands:
    @staticmethod
    def run_git_command(args: list[str], check: bool = True) -> subprocess. CompletedProcess:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=check,
        )
        return result

    @staticmethod
    def add_files(paths: Optional[list[str]] = None) -> None:
        if paths:
            GitCommands.run_git_command(["add", *paths])
        else:
            GitCommands.run_git_command(["add", "."])

    @staticmethod
    def commit_changes(files_count: int, base_name: str) -> None:
        message = f"feat: add {files_count} files to base {base_name}"
        GitCommands.run_git_command(["commit", "-m", message])

    @staticmethod
    def push_changes() -> None:
        GitCommands.run_git_command(["push", "origin", "main"])

