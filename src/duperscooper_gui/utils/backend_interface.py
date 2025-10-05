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

    # Album mode is now the default in CLI, so use --track-mode to disable it
    if not options.get("album_mode", True):
        cmd.append("--track-mode")

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

            # Exit codes: 0 = no duplicates, 2 = duplicates found, others = error
            if process.returncode not in (0, 2):
                # Check stderr for error messages
                stderr_msg = process.stderr.read() if process.stderr else ""
                error_msg = stderr_msg or "\n".join(progress_output) or "Unknown error"
                raise RuntimeError(f"Scan failed: {error_msg}")

            # Extract JSON from the output (it's at the end after all progress messages)
            # Remove ANSI codes first
            clean_output = re.sub(r"\x1b\[[0-9;]*m", "", all_output)

            # Find the start of JSON (either [ or { at start of line)
            # JSON can be multi-line, so we need to extract from first [ or { to the end
            json_start = -1
            lines = clean_output.split("\n")
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and stripped[0] in "[{":
                    json_start = i
                    break

            if json_start >= 0:
                # Extract all lines from JSON start to end
                json_lines = lines[json_start:]
                json_output = "\n".join(json_lines).strip()
            else:
                # Fallback: if no JSON found, might be empty result
                json_output = "[]"

            return json_output
        else:
            # Simple synchronous run without progress
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,  # Don't raise on non-zero exit
            )

            # Exit codes: 0 = no duplicates, 2 = duplicates found, others = error
            if result.returncode not in (0, 2):
                raise RuntimeError(f"Scan failed: {result.stderr}")

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
    List staged deletion batches using StagingManager directly.

    Returns:
        List of batch info dicts with:
        - id: Batch ID (e.g., "batch_2025-10-05_14-30-22")
        - timestamp: ISO timestamp
        - total_items_deleted: Number of items
        - total_tracks_deleted: Number of tracks
        - space_freed_bytes: Total size in bytes
        - staging_path: Path to staging directory
        - mode: "track" or "album" (inferred from total_items vs total_tracks)
    """
    try:
        from duperscooper.staging import StagingManager

        batches = StagingManager.list_batches()

        # Add mode field (infer from items vs tracks)
        for batch in batches:
            items = batch.get("total_items_deleted", 0)
            tracks = batch.get("total_tracks_deleted", 0)

            # If items == tracks, it's track mode, otherwise album mode
            batch["mode"] = "track" if items == tracks else "album"

        return batches
    except Exception as e:
        raise RuntimeError(f"List deleted failed: {e}") from e


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


def stage_items(
    paths: List[str], mode: str, store_fingerprints: bool = False
) -> Dict[str, any]:
    """
    Stage files/albums for deletion using CLI.

    Args:
        paths: List of file/album paths to stage
        mode: "track" or "album"
        store_fingerprints: Whether to store fingerprints in manifest

    Returns:
        Dict with:
            - success: bool
            - batch_id: str (UUID timestamp)
            - message: str
            - staged_count: int

    Raises:
        RuntimeError: If staging fails
    """
    # Build command - use --apply-rules with eliminate-duplicates strategy
    # This requires a JSON file as input
    import json
    import tempfile

    # Create temporary JSON file with paths marked for deletion
    if mode == "track":
        # Create track mode JSON
        json_data = {
            "mode": "track",
            "duplicate_groups": [
                {
                    "group_id": 1,
                    "hash": "temp",
                    "files": [
                        {
                            "path": path,
                            "recommended_action": "delete",
                            "is_best": False,
                        }
                        for path in paths
                    ],
                }
            ],
        }
    else:
        # Create album mode JSON
        json_data = {
            "mode": "album",
            "duplicate_groups": [
                {
                    "group_id": 1,
                    "matched_album": "temp",
                    "matched_artist": "temp",
                    "albums": [
                        {
                            "path": path,
                            "recommended_action": "delete",
                            "is_best": False,
                        }
                        for path in paths
                    ],
                }
            ],
        }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as temp_file:
        json.dump(json_data, temp_file)
        temp_path = temp_file.name

    try:
        cmd = [
            sys.executable,
            "-m",
            "duperscooper",
            "--apply-rules",
            temp_path,
            "--strategy",
            "eliminate-duplicates",
            "--execute",
            "--yes",  # Non-interactive mode
        ]

        if store_fingerprints:
            cmd.append("--store-fingerprints")

        print(f"DEBUG: Running command: {' '.join(cmd)}")  # Debug

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit
        )

        print(f"DEBUG: Command exit code: {result.returncode}")  # Debug
        print(f"DEBUG: stdout:\n{result.stdout}")  # Debug
        print(f"DEBUG: stderr:\n{result.stderr}")  # Debug

        # Parse output for batch ID
        # Look for "Staged N items to batch_YYYY-MM-DD_HH-MM-SS"
        batch_id = None
        staged_count = 0

        for line in result.stdout.splitlines():
            if "Staged" in line and "batch_" in line:
                # Extract batch ID
                import re

                match = re.search(r"batch_[\d\-_]+", line)
                if match:
                    batch_id = match.group(0)
                # Extract count
                match = re.search(r"Staged (\d+)", line)
                if match:
                    staged_count = int(match.group(1))

        if result.returncode == 0 and batch_id:
            return {
                "success": True,
                "batch_id": batch_id,
                "message": f"Successfully staged {staged_count} items to {batch_id}",
                "staged_count": staged_count,
            }
        else:
            # Check for errors
            error_msg = result.stderr or result.stdout or "Unknown error"
            return {
                "success": False,
                "batch_id": None,
                "message": f"Staging failed: {error_msg}",
                "staged_count": 0,
            }

    finally:
        # Clean up temp file
        import os

        try:
            os.unlink(temp_path)
        except Exception:
            pass
