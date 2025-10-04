"""Interface to duperscooper CLI backend via subprocess."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def run_scan(paths: List[str], options: Dict) -> str:
    """
    Run duperscooper scan and return JSON results.

    Args:
        paths: List of directory paths to scan
        options: Dict with keys:
            - album_mode: bool
            - algorithm: str ("perceptual" or "exact")
            - threshold: float
            - workers: int

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

    # No progress output (quieter for GUI)
    cmd.append("--no-progress")

    # Run command
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Scan failed: {e.stderr}") from e


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
