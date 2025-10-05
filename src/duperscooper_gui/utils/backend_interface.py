"""Interface to duperscooper CLI backend via subprocess."""

import re
import subprocess
import sys
from typing import Callable, Dict, List, Optional


def run_scan(
    paths: List[str],
    options: Dict,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> str:
    """
    Run duperscooper scan and return JSON results.

    Args:
        paths: List of directory paths to scan
        options: Dict with keys:
            - album_mode: bool
            - algorithm: str ("perceptual" or "exact")
            - threshold: float
            - workers: int
        progress_callback: Optional callback(message: str, percentage: int)

    Returns:
        JSON string with scan results

    Raises:
        RuntimeError: If scan fails
    """
    # Build command
    cmd = [sys.executable, "-m", "duperscooper"]

    # Add paths
    cmd.extend(paths)

    # Add options
    # Set min-size to 0 to scan all files (including small test files)
    cmd.append("--min-size")
    cmd.append("0")

    if options.get("album_mode"):
        cmd.append("--album-mode")

    if options.get("algorithm") == "exact":
        cmd.append("--algorithm")
        cmd.append("exact")

    if "threshold" in options:
        cmd.append("--similarity-threshold")
        cmd.append(str(options["threshold"]))

    if "workers" in options:
        cmd.append("--workers")
        cmd.append(str(options["workers"]))

    # Output JSON
    cmd.append("--output")
    cmd.append("json")

    # Progress handling
    if progress_callback:
        # Use simple progress format for GUI parsing
        cmd.append("--simple-progress")
    else:
        # No progress output
        cmd.append("--no-progress")

    # Run command
    try:
        if progress_callback:
            # Run with PTY to make subprocess think it has a real terminal
            # This ensures \r progress updates are flushed immediately
            import os
            import pty
            import select

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            # Force tqdm to output even if it doesn't detect a TTY
            env["TERM"] = "xterm-256color"

            # Create a pseudo-terminal for stdout
            # Progress and JSON both go to stdout, need PTY there
            master_fd, slave_fd = pty.openpty()

            process = subprocess.Popen(
                cmd,
                stdout=slave_fd,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                close_fds=True,
            )

            os.close(slave_fd)  # Close slave in parent process

            progress_output = []
            all_output = ""
            current_line = ""

            # Read from PTY master to get stdout with real-time \r updates
            while True:
                # Check if data is available
                readable, _, _ = select.select([master_fd], [], [], 0.1)

                if master_fd in readable:
                    try:
                        data = os.read(master_fd, 1024).decode("utf-8", errors="ignore")
                        if not data:
                            break

                        all_output += data

                        for char in data:
                            if char == "\r":
                                # Carriage return - progress update
                                if current_line.strip():
                                    # Remove ANSI color codes for callback
                                    clean_line = re.sub(
                                        r"\x1b\[[0-9;]*m", "", current_line
                                    )
                                    progress_output.append(clean_line)
                                    percentage = _parse_progress(clean_line)
                                    if percentage >= 0:
                                        progress_callback(clean_line, percentage)
                                current_line = ""
                            elif char == "\n":
                                # Newline
                                if current_line.strip():
                                    clean_line = re.sub(
                                        r"\x1b\[[0-9;]*m", "", current_line
                                    )
                                    progress_output.append(clean_line)
                                    percentage = _parse_progress(clean_line)
                                    if percentage >= 0:
                                        progress_callback(clean_line, percentage)
                                current_line = ""
                            else:
                                current_line += char
                    except OSError:
                        break

                # Check if process has finished
                if process.poll() is not None:
                    # Read any remaining data
                    try:
                        while True:
                            remaining = os.read(master_fd, 1024).decode(
                                "utf-8", errors="ignore"
                            )
                            if not remaining:
                                break
                            all_output += remaining
                    except OSError:
                        pass
                    break

            os.close(master_fd)
            process.wait()

            if process.returncode != 0:
                # Check stderr for error messages
                stderr_msg = process.stderr.read() if process.stderr else ""
                error_msg = stderr_msg or "\n".join(progress_output) or "Unknown error"
                raise RuntimeError(f"Scan failed: {error_msg}")

            # Extract JSON from the output (it's at the end after all progress messages)
            # Remove ANSI codes first
            clean_output = re.sub(r"\x1b\[[0-9;]*m", "", all_output)

            # JSON is either [] or {...} at the end of the output
            # Split by lines and find the last line that looks like JSON
            json_output = ""
            for line in reversed(clean_output.strip().split("\n")):
                line = line.strip()
                if line and line.startswith(("[", "{")):
                    json_output = line
                    break

            if not json_output:
                # Fallback: if no JSON found, might be empty result
                json_output = "[]"

            return json_output
        else:
            # Simple synchronous run without progress
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Scan failed: {e.stderr}") from e


def _parse_progress(line: str) -> int:
    """
    Parse progress percentage from progress output line.

    Args:
        line: Output line (simple format: "PROGRESS: ... (XX.X%)")

    Returns:
        Percentage (0-100) or -1 if no percentage found
    """
    # Simple progress format: "PROGRESS: Fingerprinting 10/100 (10.0%)"
    # or "PROGRESS: Scanning albums 5/10 (50.0%)"
    if line.startswith("PROGRESS:"):
        match = re.search(r"\((\d+(?:\.\d+)?)%\)", line)
        if match:
            return int(float(match.group(1)))

    return -1


def apply_rules(
    scan_results_path: str, strategy: str, execute: bool = False, **kwargs
) -> str:
    """
    Apply deletion rules to scan results.

    Args:
        scan_results_path: Path to JSON scan results
        strategy: Strategy name ("eliminate-duplicates", "keep-lossless", etc.)
        execute: If True, actually delete files (default: dry-run)
        **kwargs: Additional options (format, config, etc.)

    Returns:
        Report text

    Raises:
        RuntimeError: If apply fails
    """
    cmd = [sys.executable, "-m", "duperscooper"]

    cmd.append("--apply-rules")
    cmd.append(scan_results_path)

    cmd.append("--strategy")
    cmd.append(strategy)

    if execute:
        cmd.append("--execute")

    if "format" in kwargs:
        cmd.append("--format")
        cmd.append(kwargs["format"])

    if "config" in kwargs:
        cmd.append("--config")
        cmd.append(kwargs["config"])

    # Non-interactive mode
    cmd.append("--yes")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Apply rules failed: {e.stderr}") from e


def list_deleted() -> List[Dict]:
    """
    List staged deletion batches.

    Returns:
        List of batch info dicts
    """
    cmd = [sys.executable, "-m", "duperscooper", "--list-deleted"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse output (simple text format for now)
        # TODO: Request JSON output format for staging commands
        batches = []
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if line.strip():
                batches.append({"info": line})

        return batches
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"List deleted failed: {e.stderr}") from e


def restore_batch(batch_id: str, restore_to: str = None) -> str:
    """
    Restore a deletion batch.

    Args:
        batch_id: Batch ID to restore
        restore_to: Optional custom restore location

    Returns:
        Success message

    Raises:
        RuntimeError: If restore fails
    """
    cmd = [sys.executable, "-m", "duperscooper", "--restore", batch_id, "--yes"]

    if restore_to:
        cmd.append("--restore-to")
        cmd.append(restore_to)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Restore failed: {e.stderr}") from e


def empty_deleted(older_than: int = None, keep_last: int = None) -> str:
    """
    Permanently delete staged batches.

    Args:
        older_than: Only delete batches older than N days
        keep_last: Keep the N most recent batches

    Returns:
        Success message

    Raises:
        RuntimeError: If empty fails
    """
    cmd = [sys.executable, "-m", "duperscooper", "--empty-deleted", "--yes"]

    if older_than is not None:
        cmd.append("--older-than")
        cmd.append(str(older_than))

    if keep_last is not None:
        cmd.append("--keep-last")
        cmd.append(str(keep_last))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Empty deleted failed: {e.stderr}") from e
