# ChojemaWebDelta

**English** | [한국어](README.ko.md)

A local app that visits web pages you have registered and checks **whether anything has changed since last time**.
When you start it, a screen opens in your browser. Press **Check for changes** and the app visits the registered sites
in the background, then shows for each site whether it changed and what changed. Clicking a site's name opens the page in a new tab.

It uses no external service or AI. Everything runs on your own computer with plain rules.

## Download

The current release is [v0.2.0](https://github.com/chojema/ChojemaWebDelta/releases/tag/v0.2.0). The executables below include Python.

| OS | Supported | Download |
|---|---|---|
| Windows | 64-bit x64 | [Windows ZIP](https://github.com/chojema/ChojemaWebDelta/releases/download/v0.2.0/ChojemaWebDelta-0.2.0-windows-x64.zip) |
| macOS | Apple Silicon (M1 or later), arm64 | Coming soon |

You can verify the files with the [SHA256 checksums](https://github.com/chojema/ChojemaWebDelta/releases/download/v0.2.0/SHA256SUMS.txt).
The ZIP contains `LICENSE.txt` and `THIRD_PARTY_NOTICES.txt` along with the program.
On Intel Macs and Linux, use **Run from source** below. For the security prompts that may appear on first launch, see the instructions for each OS.

The macOS app for v0.2.0 has not been published yet. Until it is, run from source on a Mac, or use the [v0.1.0 Mac app](https://github.com/chojema/ChojemaWebDelta/releases/tag/v0.1.0), whose screen is in Korean only.

## Running

### Windows: download the executable

From the [releases page](https://github.com/chojema/ChojemaWebDelta/releases/latest), download
`ChojemaWebDelta-<version>-windows-x64.zip`, extract it, and double-click the executable inside. You do not need to install Python.
A standalone `.exe` is also provided in the same release; in that case the `LICENSE.txt` and `THIRD_PARTY_NOTICES.txt` published with the release are its license notices.

- The program is not signed, so a "Windows protected your PC" window may appear on first launch. Choose **More info → Run anyway** to start it.
- Executables bundled this way are sometimes wrongly flagged as malicious by antivirus software. If that concerns you, run from source as described below.
- To check that the download is intact, compare the output of `certutil -hashfile <file name> SHA256` with the value in the `SHA256SUMS.txt` published with the release.
- It runs without a window of its own and opens the screen in your browser. To stop it, press **Quit** on the screen.

### macOS: download the app (Apple Silicon)

From the [releases page](https://github.com/chojema/ChojemaWebDelta/releases/latest), download
`ChojemaWebDelta-<version>-macos-arm64.zip`. It is **for Apple Silicon (M1 or later) Macs**; no executable for Intel Macs is included. You do not need to install Python.
The Mac app for v0.2.0 is not available yet; until it is, the latest Mac app is in the [v0.1.0 release](https://github.com/chojema/ChojemaWebDelta/releases/tag/v0.1.0).

1. Extract the ZIP and move `ChojemaWebDelta.app` to the **Applications** folder.
2. Double-click the app and the screen opens in your browser. To stop it, press **Quit** on the screen.

- The app is only ad hoc signed; it has no Apple Developer ID signature and is not notarized. macOS may block it on first launch. Only if you trust the source, allow it under **System Settings → Privacy & Security → Open Anyway**. This option may be unavailable on Macs managed by an organization. See [Apple's instructions](https://support.apple.com/en-us/102445).
- On Intel Macs, run from source as described below.
- To check that the file is intact, compare the output of `shasum -a 256 <ZIP file name>` with the `SHA256SUMS.txt` of the release.

### Run from source (Windows, macOS, Linux)

Python 3.10 or later is required. Download this repository and run the file below.
On first run it creates a dedicated environment for your OS and installs the required packages.
Windows uses `.venv`, macOS `.venv-macos`, and Linux `.venv-linux`, so one project folder can be shared between them.

| OS | How |
|---|---|
| Windows | Double-click `run.bat` |
| macOS | Double-click `run.command` (or run `./run.sh` in Terminal) |
| Linux | Run `./run.sh` in a terminal |

If macOS or Linux reports that the file is not executable, run `chmod +x run.sh run.command` once.

To stop the app, press **Quit** on the screen or close the window it was started from.

Whichever way you start it, starting it again while it is already running opens the existing screen instead of a second copy.

## Usage

1. Register the address of a page to watch with **Add site**.
2. Press **Check for changes**. The first time a site is checked, its content at that moment is saved as the baseline for comparison.
3. From then on, sites that differ from the baseline are shown as **Changed**. **Show changes** lists the added and removed lines.
4. Once you have looked at the change, press **Mark reviewed**. The current content becomes the new baseline.
   Until you do, the change stays marked even if you check again.

Use **Sort** at the top right to order the list by status (changed sites first), newest first, oldest first, or by name.

### Screen language

The screen is available in Korean and English. It starts in your browser's language, and you can switch it with the language selector at the bottom of the screen. Your choice is remembered in that browser.

Messages in the console window follow the language of your operating system. Set the environment variable `CHOJEMA_WEBDELTA_LANG` to `ko` or `en` to fix them to one language.

### Auto-check

Choose an interval with the **Turn on auto-check** button at the top, and the app checks for changes automatically at that interval while it is running.

- Presets: Off, 1 minute, 5 minutes, 10 minutes, 30 minutes, 1 hour, 2 hours, 1 day, 1 week. With **Custom** you can set another interval in minutes, hours, or days (from 1 minute to 30 days).
- The first check happens one full interval after you set it. The interval is saved and applies the next time you start the app.
- Auto-check stops when you quit the app. If the computer wakes from sleep after the scheduled time has passed, one check runs right away.
- **A short interval can put load on this computer and your network, and frequent requests may get you blocked by the sites being checked.** The more sites you have, the longer the interval should be.

### Managing the list

**Manage list** at the top right handles the site list as a whole.

- **Export**: saves the name, address, region to watch, and patterns to ignore of every registered site to a JSON file. Saved baselines (snapshots) are not included.
- **Import**: reads an exported file and adds its sites. A site whose address, region, and patterns all match an existing one is skipped. A text file with one address per line is also accepted.
- **Delete all**: removes every registered site and its baseline. This cannot be undone, so export first.

To delete only some sites, select them with the checkbox at the left of each card and press **Delete selected**.

Imported sites get a fresh baseline on the next check. Export and import are also the way to move your list to another computer.

### When a site shows "Changed" every time although nothing changed

Parts that differ on every visit, such as view counts, dates, or ads, are being compared. Narrow the scope in the site's **Edit** dialog.

- **Region to watch**: enter a CSS selector and only that region is compared. Example: `#content`, `.board-list`
- **Patterns to ignore**: enter regular expressions, one per line, and matching text is removed before comparing. Example: `Views: \d+`

Changing the region or the patterns resets the baseline; the next check saves a new one.

### Region examples

Describe the element to watch by what identifies it in the page source. You can also click to add these from **Show region examples** in the edit dialog.

```
#content                      the element whose id is content           <div id="content">
.board-list                   elements whose class includes board-list  <ul class="board-list">
a.Link--primary               a tag together with a class               <a class="Link--primary Link">
a[href^="/releases/tag/"]     links whose address starts with this text <a href="/releases/tag/v1.0">
#content .title               .title inside #content
#notice, #schedule            two regions together
```

- Written together without a space means "matches all", a space means "inside", and a comma means "or".
- Only the text inside the selected elements is compared. Attribute values such as `href` and `class` are used only to find the elements.

### Ignore pattern examples

Text that matches a pattern is removed before comparing. You can also click to add these from **Show pattern examples** in the edit dialog. The examples shown there follow the screen language; these are the English ones.

```
(?i)views?:?\s*[\d,]+|[\d,.]+k?\s*views?        view count               Views: 1,234 / 1.2K views
\d{4}[-./]\d{1,2}[-./]\d{1,2}                   numeric date             2026-10-12 / 2026/10/12
(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}
                                                date with a month name   Oct 12, 2026 / October 12 2026
(?i)\d{1,2}:\d{2}(:\d{2})?(\s*[ap]\.?m\.?)?     time                     09:05 / 9:05:30 PM
(?i)\d+\s*(seconds?|minutes?|mins?|hours?|hrs?|days?)\s+ago
                                                elapsed time             3 minutes ago / 2 hrs ago
(?i)[\d,]+\s*(comments?|likes?|replies)|(comments?|likes?|replies)\s*\(?[\d,]+\)?
                                                comment and like counts  12 comments / Likes (3)
^.*Sponsored.*$                                 whole lines containing 'Sponsored'
^Visitors today.*$                              whole lines starting with 'Visitors today'
(?i)copyright.*$                                from copyright to the end of the line, ignoring case
```

- Only the matching part of a line is removed; the rest stays. To drop a whole line, write something like `^.*word.*$`.
- `\d` is one digit, `\s` is whitespace, `+` means one or more, `*` zero or more, and `?` optional.
- To match `. ( ) [ ] ? + * |` literally, put `\` in front. Example: `\(Ad\)`
- Runs of whitespace on the page are collapsed to a single space before the patterns are applied.
- The syntax is that of Python regular expressions. The broader a pattern, the more likely it hides a real change, so keep it narrow.

### Limitations

- Only the HTML received for the page is examined. Content filled in later by JavaScript and pages that require a login are not supported yet.
- Only text is compared. Changes to images or layout are not detected.

## Where data is stored

The site list and snapshots are stored in your user data folder, not in the program folder. The actual path is shown at the bottom of the screen.

| OS | Location |
|---|---|
| Windows | `%APPDATA%\ChojemaWebDelta` |
| macOS | `~/Library/Application Support/ChojemaWebDelta` |
| Linux | `~/.local/share/ChojemaWebDelta` |

Set the environment variable `CHOJEMA_WEBDELTA_DATA` to use a different folder.

## Uninstalling

There is no uninstaller. The app registers nothing in the registry, the Start menu, startup items, or background services, so you only need to remove the two things below.

1. Stop the app with **Quit** on the screen.
2. Delete the program and the data folder.

| | Windows | macOS |
|---|---|---|
| Program | The downloaded `ChojemaWebDelta-…-windows-x64.exe` | `ChojemaWebDelta.app` |
| Data folder | `%APPDATA%\ChojemaWebDelta` | `~/Library/Application Support/ChojemaWebDelta` |
| Opening the data folder | Type `%APPDATA%\ChojemaWebDelta` in the File Explorer address bar | In Finder, choose **Go → Go to Folder** (⇧⌘G) and enter `~/Library/Application Support/ChojemaWebDelta` |

`AppData` on Windows and the user `Library` folder on macOS are hidden by default, so open the data folder as described above. The **Applications** folder on macOS is not hidden, and an app moved there can be found in Finder. On Linux the data folder is `~/.local/share/ChojemaWebDelta`.

- **To keep your list**, save it with **Manage list → Export** before deleting.
- **If you have been using the scripts (`run.bat`, `run.sh`, `run.command`)**, delete the whole downloaded project folder instead of a program. The dedicated Python environments (`.venv`, `.venv-macos`, `.venv-linux`) are inside it.
- **If you set another folder with `CHOJEMA_WEBDELTA_DATA`**, the data is in that folder.
- **To keep the app but return to a clean state**, delete only the data folder. The next start begins with an empty list.

Two other things may remain; leaving them does no harm.

- The list sort order and screen language remembered by your browser. Clearing the site data for `127.0.0.1` in your browser settings removes them.
- On Windows, if the app was force-closed, a folder whose name starts with `_MEI` in the temporary folder (`%TEMP%`). It is removed automatically on a normal exit, and can be deleted if it remains.

## Development

```
python -m pip install -r requirements.txt
python -m chojema_webdelta            # run (options: --port, --no-browser)
python -m unittest discover -s tests -t .   # tests
```

| File | Role |
|---|---|
| `chojema_webdelta/engine.py` | Fetching pages, extracting the region, comparing |
| `chojema_webdelta/store.py` | Storing the site list and snapshots (SQLite) |
| `chojema_webdelta/server.py` | Local screen server, API, background checks |
| `chojema_webdelta/i18n.py` | Korean and English text for server errors and console output |
| `chojema_webdelta/web/` | The screen (HTML, CSS, JS) |
| `chojema_webdelta/web/messages.json` | Korean and English text for the screen |

### Building an executable

This builds a file that runs on computers without Python. Only the file for the OS you build on is produced.

```
python -m pip install pyinstaller
python packaging/build.py
```

It produces `dist/ChojemaWebDelta.exe` on Windows and `dist/ChojemaWebDelta.app` on macOS.
The build collects the licenses of the installed dependencies and the Python runtime notices and includes them in the program. On Windows it also creates `dist/ChojemaWebDelta-windows-<architecture>.zip`, which contains the executable together with the notices.

On macOS, the following command creates the dedicated environment, installs the dependencies, and builds the app in one step.

```sh
bash packaging/build_macos.sh
```

The Mac environment is kept in `.venv-macos` and intermediate build files in `build/macos`.
The existing Windows `.venv` and `dist/ChojemaWebDelta.exe` are left untouched.
Double-clicking the built `dist/ChojemaWebDelta.app` opens the screen in your browser; the Mac it runs on does not need Python installed.
The script builds an app for the CPU architecture of the Mac it runs on.
It also creates `dist/ChojemaWebDelta-macos-<architecture>.zip`. If Finder metadata gets re-attached to the app in a synced folder and signature verification fails, extract the ZIP in a folder that is not synced and run it from there.
The Mac app uses an ad hoc signature for local use and does not include Apple's distribution signature or notarization.

## License

The original code of ChojemaWebDelta (including v0.1.0) is provided under the [MIT License](LICENSE).
You may use, modify, and redistribute it commercially, provided the copyright and license notices are kept.

The bundled Python runtime and third-party libraries are under their own licenses. The full notices and the locations of the original sources are in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
When you redistribute the program, provide `LICENSE.txt` and `THIRD_PARTY_NOTICES.txt` with it.
