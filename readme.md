# OnshapeDRPC

Discord Rich Presence for Onshape on Windows, with per-document blur settings and accurate labels for the tab you are viewing.

```text
Onshape
Part Studio: Intake · Sketch 1
Document: Robot Design
[Sketch feature badge with a small Onshape badge]
```

## Features

- Displays **Onshape** with your current document and selected tab.
- Identifies **Part Studio**, **Assembly**, **Drawing**, **Variable Studio**, **Bill of Materials**, and imported files.
- Reads the selected Onshape page URL through Windows accessibility, including installed Onshape browser apps. Duplicate tab names and non-default workspaces are resolved using their IDs.
- Uses the Onshape logo and provides a **View in Onshape** button; document access is enforced by Onshape.
- Part Studios show the open feature editor (Sketch, Extrude, Fillet, and other tools), or **Idle** when no feature is being edited. Feature badges replace model previews and require no Onshape API calls.
- Assemblies show model snapshots. Always blurs Biobuzz; other documents show clear Assembly previews by default. Add more protected documents by name or ID.
- Checks for tab changes every half-second, submits changed activity at least 5 seconds apart, and refreshes each preview about once every two hours when budget allows.
- Runs silently, starts at Windows login, reconnects when Discord becomes available, and prevents duplicate instances.
- Keeps rotating local diagnostic logs instead of requiring a console window.

## Requirements

- Windows 10 or 11 on an x64 computer.
- Python 3.10 or newer, available as `python` on PATH.
- The Discord desktop application.
- An Onshape account and API access/secret keys with permission to read the relevant documents.
- Brave, Chrome, Edge, or Firefox. URL detection is verified with Brave's installed Onshape app; support depends on the browser exposing the selected page through Windows accessibility.
- Internet access to Onshape, Discord, and Cloudflare Tunnel.

## Install

Open PowerShell in the folder where you want to keep the application:

```powershell
git clone https://github.com/SrijanCherupally/OnshapeDRPC.git
cd OnshapeDRPC
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup creates a virtual environment, installs Python dependencies, creates `.env` if needed, and downloads the official Cloudflare Tunnel helper. The helper must have a valid Windows signature identifying Cloudflare.

### Configure Onshape credentials

Create API keys in [Onshape's developer portal](https://dev-portal.onshape.com/keys). Read [Onshape's authentication documentation](https://onshape-public.github.io/docs/auth/apikeys/) for account/API access details.

The application accepts the existing integration's Basic authentication format: Base64-encoded UTF-8 text containing `ACCESS_KEY:SECRET_KEY`. Base64 is encoding, **not encryption**. Treat the resulting value like a password.

Generate and save it locally without printing it:

```powershell
$taskAccessKey = Read-Host 'Onshape access key'
$taskSecretInput = Read-Host 'Onshape secret key' -AsSecureString
$taskSecretKey = [System.Net.NetworkCredential]::new('', $taskSecretInput).Password
$taskEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($taskAccessKey + ':' + $taskSecretKey))
Set-Content -LiteralPath .env -Value ('API_KEY=' + $taskEncoded) -Encoding UTF8
Remove-Variable taskAccessKey, taskSecretInput, taskSecretKey, taskEncoded
```

`.env` is ignored by Git. Never publish it, its contents, or an example file containing real credentials.

### Start silently

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Open Discord and an Onshape document. The selected tab should appear on your Discord profile after a local check and the next activity submission. Changed submissions are at least 5 seconds apart; Discord delivery can add latency. Image rendering runs in the background and does not hold up tab labels.

### Start automatically at login

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-startup.ps1
```

This installs `OnshapeDRPC.lnk` in your Windows Startup folder. It runs `venv\Scripts\pythonw.exe main.py` with this project as the working directory. Windows restart is handled when you next sign in.

To disable automatic startup, open `shell:startup` using Win + R and delete `OnshapeDRPC.lnk`. To stop a currently running instance, end the Python process belonging to this project in Task Manager. Re-running the launcher while an instance is running does not start a second copy.

## Per-Document Blur and Document Privacy

Discord cannot enforce Onshape document permissions for Rich Presence images. This app displays previews publicly, using blur rules for protected documents, while the **View in Onshape** button opens the full model with Onshape's normal sign-in and document access checks.

For Assemblies, the app reads the model bounding box and requests a fresh 600 x 600 isometric shaded render. The camera is centered on the model and its scale is chosen to include every projected bounding-box corner, preventing the clipping present in some cached Onshape thumbnails. If the Assembly render API is unavailable, the app uses a 300 x 170 generated Assembly thumbnail as a fallback. Part Studios never request or display model previews. Drawing and other tab types use the Onshape logo.

Pillow removes unused transparent background and fits all visible geometry proportionally into the square Discord preview, with a small border to keep the blurred edges inside the image. Only empty background is cropped. Clear previews retain a 600 x 600 canvas with the same proportional fit and border. The blur stays at 64 x 64 detail reduction and an 8-pixel Gaussian blur on a 300 x 300 canvas. This obscures small details while retaining the general shape. Original image metadata is discarded.

Only the processed PNG permitted by the document rules is placed in the image server's memory. Biobuzz and other protected documents are always blurred before sharing. Other documents are shared as clear, fitted previews. If processing fails, the app uses the logo; protected documents never fall back to clear images.

A local server on 127.0.0.1:19288 serves the processed preview at an unpredictable path. A [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) gives Discord a temporary HTTPS URL. The server exposes no credentials, CAD files, directory browsing, or general-purpose API proxy. Other paths return 404.

**Every shared preview, clear or blurred, is accessible to anyone with its URL and is processed by Cloudflare and Discord. Blurring is a visual treatment, not an access-control guarantee.** Document and tab names are also visible to anyone who can view your Discord activity. People may still recognize the model's silhouette. Existing unblurred images from earlier revisions may remain in Discord caches; the app cannot revoke cached copies.

Assembly snapshots are isometric API renders or fallback thumbnails rather than captures of your exact viewport. They change when you switch elements and are checked about every 120 minutes when budget allows. Some element types have no suitable thumbnail. The logo is used if a thumbnail or tunnel is unavailable. Old paths are removed when the current preview changes or no visible Onshape window is found.

Quick Tunnels need no Cloudflare account, but are intended for testing and development and have no uptime guarantee. Their hostname changes at app restart; the presence updates automatically. The helper launches silently at login and retries after exiting. This integration remains experimental.

### Choose which documents are blurred

Biobuzz is always blurred, matched case-insensitively by name. This installation also pins the current Biobuzz document ID in the ignored local settings file, so it stays blurred even after a rename.

Edit `snapshot-settings.json` to add protected names or IDs:

```json
{
  "blurred_document_names": ["Biobuzz", "Another Private Design"],
  "blurred_document_ids": []
}
```

Use `snapshot-settings.local.json` with the same fields for personal rules that should not be committed to Git. Local rules add to the shared rules; they cannot remove protections. New installations can add the Biobuzz document ID from its Onshape URL to protect it after renaming. The built-in Biobuzz name rule cannot be accidentally disabled by deleting the example settings entry.

Other documents show clear previews. Settings are re-read on each presence update, normally within half a second. Changing a rule removes the old image path immediately. The new permitted preview is loaded from cache or rendered in the background; the logo is used while a new preview is unavailable. Invalid settings make all previews blurred until fixed. Previously cached Discord images cannot be revoked.

## Part Studio Feature Activity

The persistent local accessibility helper reads only the open `feature-dialog` panel. Its help topic identifies built-in feature types, including renamed Sketches and Extrudes; the editor title supplies the feature name. Unrecognized custom features show `Feature: <editor name>`. Toolbar tools and saved feature-list entries are never treated as active editing.

The last feature remains visible after its editor closes, until **15 minutes** pass without using a feature. An open editor also goes idle after 15 minutes without interaction. Local Windows input timing counts only while the selected Onshape window is in the foreground; using other applications does not reset the timer. Each Part Studio retains its own most recent feature during the current app session. Before a feature has been observed, the status is Viewing during the initial grace period. Feature activity is read about once a second and uses the existing 5-second minimum between changed Discord submissions.

Assemblies show their snapshots during use and switch to the branded Idle card after 15 minutes without local interaction. Interacting with the Assembly resumes the snapshot. Idle Assemblies do not request new snapshots. The inactivity tracker uses no Onshape API calls and reads only input timestamps, not typed characters.

Part Studios show a locally generated feature badge instead of a CAD snapshot. The badges use bundled native Onshape feature icons, with their original artwork fitted onto a light tile for contrast. Idle uses the Onshape logo on a dark green backdrop. Assemblies use the native Assembly icon as their small badge while retaining the model snapshot. Only the feature type is drawn in the badge; the editor name appears alongside the Part Studio name and in image hover text. The document always has its own line underneath. Default names such as Extrude 72 are shown once, without a repeated Extrude prefix. Icon source URLs are recorded in assets/onshape-icons/sources.json; unknown custom features use Onshape branding. Badges use the same tunnel as Assembly previews and require no Onshape API requests. Feature names are visible to people who can see your Discord activity. Assemblies keep their fitted previews and existing blur rules.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No presence | Open the Discord desktop app and an Onshape window; inspect `presence.log`. |
| Logo instead of preview | Allow time for the tunnel to connect; check that the element has a PNG thumbnail and Cloudflare is reachable. |
| Generic `Tab` label | The selected page URL was unavailable and the window title matched duplicate element names. |
| Wrong window | With multiple Onshape windows, the foremost visible Onshape window is used. Background tabs inside another browser window are not monitored. |
| Document is not found | Verify API access. URL detection is preferable; title fallback only uses the default workspace and refuses duplicate document names. |
| Startup fails | Keep the project in the same location and rerun `setup.ps1` and `install-startup.ps1` after moving it. |
| Display name differs | The app requests `Onshape`; Discord behavior can depend on the configured Rich Presence application. |

For visible debugging:

```powershell
.\venv\Scripts\python.exe main.py
```

Do not run this alongside an existing background instance. `presence.log` rotates at 500 KB with two backups. Logs are ignored by Git.

## Low-Usage Mode: 400 Hours per Year

The app checks local browser tabs every half-second and reads an unchanged window URL every second. A persistent accessibility helper avoids repeatedly starting PowerShell. These local checks do not use the Onshape API. Changed Discord submissions are at least 5 seconds apart; Discord delivery can add latency. Background image requests never hold up tab labels, though uncached document metadata can require an API request.

The app targets two API calls per active hour. API credit accrues only while the app observes a visible Onshape document window. Six initial calls allow first-time setup, and no more than six unused credits can be held. Every outgoing API request, including failed attempts and fallback thumbnail requests, consumes credit. A persistent hard cap stops requests after 1,000 attempts. Restarting the app does not reset credit or the cap, and resuming Windows from sleep does not award a large burst of credit.

This targets roughly 800 earned calls across 400 active hours, plus up to six initial calls, instead of hundreds of calls per hour. The hard cap also limits bursts or unusual tab-switching patterns. For [Free, EDU Student, and Standard accounts, Onshape currently lists 2,500 calls annually](https://onshape-public.github.io/docs/auth/limits/), leaving approximately 1,500 for other integrations **if at least 2,500 calls remain at setup**. Calls consumed before this change are still part of your current allowance; the app cannot refund them or read the account's remaining quota from its local counter.

Metadata is cached for a day and saved in metadata-cache.json. Processed previews are saved under preview-cache/ and normally refreshed every 120 minutes. Returning to a saved tab or restarting reuses its preview without additional requests. Biobuzz remains blurred, including saved previews.

When credit is exhausted, known tab types and old images remain available. A newly visited tab can show a generic Tab label or the Onshape logo until credit is available. Browser document/tab names and exact links still come from the local window URL. Invalid budget state disables API requests rather than refilling credit.

The budget is tracked in api-budget.json, excluded from Git along with the metadata and previews. Its used counter counts this app's attempts from the time low-usage mode was installed; it is not your Onshape account usage counter. The 1,000-call cap does not reset automatically because Onshape's allowance cycle may differ from the calendar year. Once your account allowance renews, stop the app, archive api-budget.json, and restart to start a new app budget. Do not reset it during the current allowance period.

Renders use 600 x 600 source pixels, and clear previews retain that resolution. Biobuzz keeps the existing blur strength and 300 x 300 processed canvas. Resolution changes affect rendering work and transferred bytes, not API call counts. Part Studio feature detection uses zero Onshape requests, and Part Studio preview requests are disabled. Each successful Assembly refresh normally uses two calls (bounds plus render). Two-hour refreshes therefore use roughly 400 calls over 400 hours of a single continuously viewed tab, plus metadata and any fallback requests. First visits to additional tabs can need previews sooner; the two-call hourly credit rate and 1,000-call hard cap still apply.

On the development PC, the first local URL read took about 0.38 seconds, and subsequent reads with the persistent helper took about 0.02–0.04 seconds. Timing depends on browser accessibility and document size.

## Development

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m py_compile main.py active_url.py activity_tracker.py feature_activity.py feature_badge.py snapshot_bridge.py api_budget.py
```

The local instance guard uses port 19287; the image server uses port 19288. snapshot-status.json contains the current preview URL and blur state and is ignored by Git. API calls have timeouts; metadata and processed previews are saved locally across restarts.

## Credits

Based on [IIRoan/OnshapeDRPC](https://github.com/IIRoan/OnshapeDRPC). This version adds selected-tab URL detection, blurred model previews, permission-enforced document links, silent startup helpers, reconnection, and diagnostics. Onshape and Discord are trademarks of their respective owners. This project is unofficial.

The upstream repository does not include a license file. This repository preserves attribution and does not add a license granting rights to upstream code.
