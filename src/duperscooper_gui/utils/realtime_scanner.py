"""Real-time scanner that emits groups as they're found."""

from typing import Any, Dict, List

from PySide6.QtCore import QThread, Signal


class RealtimeScanThread(QThread):
    """Background thread for running scans with real-time group emission."""

    progress = Signal(str, int)  # Emits (message: str, percentage: int)
    group_found = Signal(dict)  # Emits each group as it's found
    finished = Signal()  # Emits when scan is complete
    error = Signal(str)  # Emits error messages
    processing_started = Signal()  # Emits when processing phase starts

    def __init__(self, paths: List[str], mode: str):
        super().__init__()
        self.setObjectName(f"ScanThread-{mode}")  # Set thread name for debugging
        self.paths = paths
        self.mode = mode
        self._should_stop = False
        self._stop_and_process = False
        self._stop_processing = False

    def stop(self) -> None:
        """Request the scan to stop completely."""
        self._should_stop = True

    def stop_and_process(self) -> None:
        """Request to stop directory scanning but process albums found so far."""
        self._stop_and_process = True

    def stop_processing(self) -> None:
        """Request to stop the processing phase (metadata/duplicate finding)."""
        self._stop_processing = True

    def run(self) -> None:
        """Run the scan in background thread."""
        try:
            if self.mode == "track":
                self._run_track_scan()
            else:
                self._run_album_scan()

            # Note: QThread automatically emits finished signal when run() exits
            # No need to manually emit it here

        except Exception as e:
            self.error.emit(str(e))

    def _run_track_scan(self) -> None:
        """Run track mode scan with real-time group emission."""
        from pathlib import Path

        from duperscooper.finder import DuplicateFinder, DuplicateManager
        from duperscooper.hasher import AudioHasher

        # Convert string paths to Path objects
        path_objects = [Path(p) for p in self.paths]

        # Create components with shared cache
        cache_path = Path.home() / ".config" / "duperscooper" / "hashes.db"
        hasher = AudioHasher(
            cache_path=cache_path, use_cache=True, cache_backend="sqlite"
        )

        # Create finder with correct parameters
        finder = DuplicateFinder(
            min_size=0,
            algorithm="perceptual",
            similarity_threshold=98.0,
            use_cache=True,
            cache_backend="sqlite",
            max_workers=8,
        )
        # Use the hasher with our cache
        finder.hasher = hasher

        # Find duplicates (returns dict mapping group_id -> (files, fingerprints))
        duplicate_groups = finder.find_duplicates(path_objects)

        if self._should_stop:
            return

        # Process each group and emit
        for group_id, (files, fingerprints) in enumerate(
            duplicate_groups.items(), start=1
        ):
            if self._should_stop:
                return

            # Build file_list as list of (path, fingerprint) tuples
            file_list = list(zip(files, fingerprints))

            # Identify best quality file (static method)
            best_file, best_fp, enriched_files = (
                DuplicateManager.identify_highest_quality(file_list, hasher)
            )

            # Build group data in same format as CLI JSON output
            group_data: Dict[str, Any] = {
                "group_id": group_id,
                "files": [],
            }

            # enriched_files: list of (path, fp, metadata, quality, similarity)
            for file_path, _fp, metadata, quality_score, similarity in enriched_files:
                group_data["files"].append(
                    {
                        "path": str(file_path),
                        "size_bytes": metadata.get("size", 0),
                        "audio_info": metadata.get("audio_info", ""),
                        "quality_score": quality_score,
                        "similarity_to_best": similarity,
                        "is_best": file_path == best_file,
                        "recommended_action": (
                            "keep" if file_path == best_file else "delete"
                        ),
                    }
                )

            # Emit group
            self.group_found.emit(group_data)

            # Update progress
            percentage = int((group_id / len(duplicate_groups)) * 100)
            self.progress.emit(
                f"Processing group {group_id}/{len(duplicate_groups)}", percentage
            )

    def _run_album_scan(self) -> None:
        """Run album mode scan with real-time group emission."""
        from pathlib import Path

        from duperscooper.album import AlbumDuplicateFinder, AlbumScanner
        from duperscooper.hasher import AudioHasher

        # Convert string paths to Path objects
        path_objects = [Path(p) for p in self.paths]

        # Debug: print paths
        self.progress.emit(
            f"DEBUG: Scanning paths: {[str(p) for p in path_objects]}", 5
        )

        # Create components with shared cache
        cache_path = Path.home() / ".config" / "duperscooper" / "hashes.db"
        hasher = AudioHasher(
            cache_path=cache_path, use_cache=True, cache_backend="sqlite"
        )
        scanner = AlbumScanner(hasher)

        # Scan for albums
        self.progress.emit(f"Scanning {len(path_objects)} path(s) for albums...", 10)

        # Scan albums with progress callback (includes directory discovery)
        # Track last reported percentage to avoid spamming UI with updates
        self._last_reported_pct = -1

        def on_scan_progress(message: str, percentage: int) -> None:
            # Emit every 1% for frequent updates (for testing)
            # TODO: Change to % 10 == 0 for production to reduce spam
            if percentage % 1 == 0 or percentage == 100:
                # Map 0-100% of scanning to 20-90% of total progress
                adjusted_percentage = 20 + int(percentage * 0.7)
                self.progress.emit(message, adjusted_percentage)

        # Define separate stop callbacks for different phases
        def dir_scan_should_stop() -> bool:
            """Check if directory scanning should stop (both stop types)."""
            return self._should_stop or self._stop_and_process

        def processing_should_stop() -> bool:
            """Check if processing should stop."""
            return self._should_stop or self._stop_processing

        def on_metadata_start() -> None:
            """Callback when metadata extraction starts."""
            self.processing_started.emit()

        albums = scanner.scan_albums(
            path_objects,
            progress_callback=on_scan_progress,
            should_stop=processing_should_stop,  # For metadata extraction
            should_stop_dir_scan=dir_scan_should_stop,  # For directory discovery
            on_metadata_start=on_metadata_start,  # Signal when processing starts
        )

        # Check if we should stop completely (takes precedence over stop_and_process)
        if self._should_stop or self._stop_processing:
            return

        # If stop_and_process was requested, show appropriate message
        if self._stop_and_process:
            self.progress.emit(
                f"Directory scan stopped, processing {len(albums)} albums found...", 91
            )
        else:
            self.progress.emit(f"Found {len(albums)} albums, finding duplicates...", 91)

        # Find duplicate albums (strategy is only parameter, no similarity_threshold)
        finder = AlbumDuplicateFinder(hasher)

        def check_stop() -> bool:
            result = self._should_stop or self._stop_processing
            if result:
                print(
                    f"DEBUG: check_stop() returning True, "
                    f"_should_stop={self._should_stop}, "
                    f"_stop_processing={self._stop_processing}"
                )
            return result

        # Create progress callback that forwards to our progress signal
        def progress_cb(message: str, percentage: int) -> None:
            self.progress.emit(message, percentage)

        duplicate_groups = finder.find_duplicates(
            albums,
            strategy="auto",
            should_stop=check_stop,
            progress_callback=progress_cb,
        )

        if self._should_stop or self._stop_processing:
            return

        # Process each group and emit
        for group_id, albums_in_group in enumerate(duplicate_groups, start=1):
            if self._should_stop or self._stop_processing:
                return

            # Get matched album/artist info
            matched_album, matched_artist = finder.get_matched_album_info(
                albums_in_group
            )

            # Identify best quality album
            best_album = max(albums_in_group, key=lambda a: a.avg_quality_score)

            # Build group data
            group_data: Dict[str, Any] = {
                "group_id": group_id,
                "matched_album": matched_album,
                "matched_artist": matched_artist,
                "albums": [],
            }

            for album in albums_in_group:
                # Calculate confidence
                confidence = finder.calculate_confidence(album, albums_in_group)

                # Calculate match percentage (similarity to best)
                if album == best_album:
                    match_percentage = 100.0
                else:
                    match_percentage = finder.album_similarity(album, best_album)

                group_data["albums"].append(
                    {
                        "path": str(album.path),
                        "track_count": album.track_count,
                        "size_bytes": album.total_size,
                        "quality_info": album.quality_info,
                        "quality_score": album.avg_quality_score,
                        "match_percentage": match_percentage,
                        "match_method": (
                            "musicbrainz"
                            if album.musicbrainz_albumid
                            else "fingerprint"
                        ),
                        "is_best": album == best_album,
                        "recommended_action": (
                            "keep" if album == best_album else "delete"
                        ),
                        "musicbrainz_albumid": album.musicbrainz_albumid,
                        "disc_number": album.disc_number,
                        "disc_subtitle": album.disc_subtitle,
                        "total_discs": album.total_discs,
                        "album_name": album.album_name,
                        "artist_name": album.artist_name,
                        "confidence": confidence,
                    }
                )

            # Emit group
            self.group_found.emit(group_data)

            # Update progress
            percentage = 92 + int((group_id / len(duplicate_groups)) * 8)
            self.progress.emit(
                f"Processing group {group_id}/{len(duplicate_groups)}", percentage
            )
