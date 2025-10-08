"""Real-time scanner that emits groups as they're found."""

from typing import List

from PySide6.QtCore import QThread, Signal


class RealtimeScanThread(QThread):
    """Background thread for running scans with real-time group emission."""

    progress = Signal(str, int)  # Emits (message: str, percentage: int)
    group_found = Signal(dict)  # Emits each group as it's found
    finished = Signal()  # Emits when scan is complete
    error = Signal(str)  # Emits error messages

    def __init__(self, paths: List[str], mode: str):
        super().__init__()
        self.paths = paths
        self.mode = mode
        self._should_stop = False

    def stop(self):
        """Request the scan to stop."""
        self._should_stop = True

    def run(self) -> None:
        """Run the scan in background thread."""
        try:
            if self.mode == "track":
                self._run_track_scan()
            else:
                self._run_album_scan()

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def _run_track_scan(self):
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
        for group_id, (files, fingerprints) in enumerate(duplicate_groups, start=1):
            if self._should_stop:
                return

            # Build file_list as list of (path, fingerprint) tuples
            file_list = list(zip(files, fingerprints))

            # Identify best quality file (static method)
            best_file, best_fp, enriched_files = (
                DuplicateManager.identify_highest_quality(file_list, hasher)
            )

            # Build group data in same format as CLI JSON output
            group_data = {
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

    def _run_album_scan(self):
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

        # Debug: Check if paths exist
        for p in path_objects:
            exists = p.exists()
            is_dir = p.is_dir() if exists else False
            self.progress.emit(f"DEBUG: Path {p} - exists={exists}, is_dir={is_dir}", 5)

        # Scan for albums
        self.progress.emit("Scanning for albums...", 10)

        # Debug: Manually check for album directories
        album_dirs = scanner._find_album_directories(path_objects)
        self.progress.emit(
            f"DEBUG: _find_album_directories returned {len(album_dirs)} dirs", 12
        )
        if album_dirs:
            self.progress.emit(
                f"DEBUG: First few dirs: {[str(d) for d in album_dirs[:3]]}", 13
            )

            # Debug: Try extracting metadata from first album
            try:
                _ = scanner.extract_album_metadata(album_dirs[0])
                self.progress.emit(
                    f"DEBUG: Successfully extracted metadata from {album_dirs[0]}", 14
                )
            except Exception as e:
                self.progress.emit(
                    f"DEBUG: FAILED to extract metadata from {album_dirs[0]}: {e}", 14
                )

        albums = scanner.scan_albums(path_objects)

        # Debug: print album count
        self.progress.emit(f"DEBUG: Found {len(albums)} albums total", 20)

        if self._should_stop:
            return

        self.progress.emit(f"Found {len(albums)} albums, finding duplicates...", 30)

        # Find duplicate albums (strategy is only parameter, no similarity_threshold)
        finder = AlbumDuplicateFinder(hasher)
        duplicate_groups = finder.find_duplicates(albums, strategy="auto")

        if self._should_stop:
            return

        # Process each group and emit
        for group_id, albums_in_group in enumerate(duplicate_groups, start=1):
            if self._should_stop:
                return

            # Get matched album/artist info
            matched_album, matched_artist = finder.get_matched_album_info(
                albums_in_group
            )

            # Identify best quality album
            best_album = max(albums_in_group, key=lambda a: a.avg_quality_score)

            # Build group data
            group_data = {
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
                        "album_name": album.album_name,
                        "artist_name": album.artist_name,
                        "confidence": confidence,
                    }
                )

            # Emit group
            self.group_found.emit(group_data)

            # Update progress
            percentage = 30 + int((group_id / len(duplicate_groups)) * 70)
            self.progress.emit(
                f"Processing group {group_id}/{len(duplicate_groups)}", percentage
            )
