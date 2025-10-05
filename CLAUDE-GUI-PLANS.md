# CLAUDE GUI PLANS

1. the results viewer contains color combinations that hard to read. in particular, the "Group n" headings are shown in white on a light grey background.

2. remove the " (avg)" from the quality column in the individual table rows and add it to the column header instead

3. remove the "results viewer coming soon" test from the results viewer

4. add Album and Artist columns to the results entries. pull this from metadata or show an empty cell if no metadata is available for either of these fields.

5. [FUTURE] let the user right-click on a duplicate entry in the results viewer to view properties of that file. properties should include the location and size of the file, sha hash, fingerprint, and available metadata (album, artist, musicbrainz tags)

6. [FUTURE] The GUI must have a settings/preferences/options panel, accessible through the menus in accordance with per-OS best practices (this means it could be in a different menu location on MacOS vs Linux vs Windows)

7. The GUI should be cross-platform. It should work on Linux, MacOS and Windows.

8. [FUTURE] The GUI should keep track of files that have been deleted in the current session for the user to easily call up and start a restoration.

9. [FUTURE] The GUI should make it easy to recall deletions from previous sessions (maybe keep track of manifests that were created in past sessions)

10. [FUTURE] the user should have the ability to open the log output in a larger scrollable window or an external program. the GUI should also have the facility to save the log output.
