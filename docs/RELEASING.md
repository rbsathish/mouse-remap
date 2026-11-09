# Releasing

There is deliberately **no CI workflow** in this repository (no GitHub Actions), so pushing never spends build
minutes. Releases are built and checked on your own machine.

## Steps

1. **Version.** Edit `_version.py` (`MAJOR.MINOR.PATCH`). Patch for fixes, minor for new features, major for
   incompatible changes to settings.
2. **Changelog.** Add a section to `CHANGELOG.md` and copy its text into `docs/releases/v<version>.md` (this becomes
   the release description).
3. **Test.** Run `test.bat`; all checks must pass.
4. **Build.** Run `build.bat`. It writes:
   - `dist\MouseRemap.exe` (with the version in its file properties)
   - `dist\MouseRemap-<version>-win64.zip` (exe + README + changelog + license)
   - `dist\MouseRemap-<version>-win64.zip.sha256`
5. **Check the exe** by running it: the tray tooltip and the bottom of the window should show the new version.
6. **Commit and tag.**
   ```bat
   git add -A
   git commit -m "Release v<version>"
   git tag -a v<version> -m "v<version>"
   git push origin main --follow-tags
   ```
7. **Publish the release** (this uploads the zip, so do it only when you are ready for it to be downloadable):
   ```bat
   gh release create v<version> dist\MouseRemap-<version>-win64.zip dist\MouseRemap-<version>-win64.zip.sha256 ^
       --title "Mouse Button Remap v<version>" --notes-file docs\releases\v<version>.md
   ```

If the repository is private, only people with access can download the release. Visibility is under Settings > General >
Danger Zone.

## Commit identity

Commits and tags in this repository use the account's GitHub `noreply` address (set in the repository's local git
config), so no real email address is published. Keep it that way: check `git log -1 --format='%ae %ce'` and
`git cat-file -p v<version>` before pushing.
