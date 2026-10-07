# OnshapeDRPC

Discord Rich Presence for Onshape on Windows, with heavily blurred model snapshots and accurate labels for the tab you are viewing.

```text
Onshape
Part Studio: Intake
Document: Robot Design
[Blurred model silhouette with a small Onshape badge]
```

## Features

- Displays **Onshape** with your current document and selected tab.
- Identifies **Part Studio**, **Assembly**, **Drawing**, **Variable Studio**, **Bill of Materials**, and imported files.
- Reads the selected Onshape page URL through Windows accessibility, including installed Onshape browser apps. Duplicate tab names and non-default workspaces are resolved using their IDs.
- Uses the Onshape logo and provides a **View in Onshape** button; document access is enforced by Onshape.
- Displays a heavily blurred thumbnail while preserving the overall model silhouette.
- Updates tab selection every 15 seconds and checks previews every 90 seconds.
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

Open Discord and an Onshape document. The selected tab should appear on your Discord profile within about 15 seconds.

### Start automatically at login

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-startup.ps1
```

This installs `OnshapeDRPC.lnk` in your Windows Startup folder. It runs `venv\Scripts\pythonw.exe main.py` with this project as the working directory. Windows restart is handled when you next sign in.

To disable automatic startup, open `shell:startup` using Win + R and delete `OnshapeDRPC.lnk`. To stop a currently running instance, end the Python process belonging to this project in Task Manager. Re-running the launcher while an instance is running does not start a second copy.

## Blurred Snapshots and Document Privacy

Discord cannot enforce Onshape document permissions for Rich Presence images. This app displays a deliberately blurred preview publicly, while the **View in Onshape** button opens the full model with Onshape's normal sign-in and document access checks.

For Assemblies and Part Studios, the app reads the model bounding box and requests a fresh isometric shaded render. The camera is centered on the model and its scale is chosen to include every projected bounding-box corner, preventing the clipping present in some cached Onshape thumbnails. Other tab types, or unavailable render APIs, use a wider generated thumbnail as a fallback.

Pillow removes unused transparent background and fits all visible geometry proportionally into the square Discord preview, with a small border to keep the blurred edges inside the image. Only empty background is cropped. The blur stays at 64 x 64 detail reduction and an 8-pixel Gaussian blur on a 300 x 300 canvas. This obscures small details while retaining the general shape. Original image metadata is discarded.

Only the resulting blurred PNG is placed in the image server's memory. Original thumbnails are never exposed by the server. If image decoding or blurring fails, the app uses the Onshape logo; it never falls back to sharing an unblurred image.

A local server on 127.0.0.1:19288 serves the blurred image at an unpredictable path. A [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) gives Discord a temporary HTTPS URL. The server exposes no credentials, CAD files, directory browsing, or general-purpose API proxy. Other paths return 404.

**The blurred image is accessible to anyone with its URL and is processed by Cloudflare and Discord. Blurring is a visual treatment, not an access-control guarantee.** Document and tab names are also visible to anyone who can view your Discord activity. People may still recognize the model's silhouette. Existing unblurred images from earlier revisions may remain in Discord caches; the app cannot revoke cached copies.

Snapshots are isometric API renders or fallback thumbnails rather than captures of your exact viewport. They change when you switch elements and are checked every 90 seconds. Some element types have no suitable thumbnail. The logo is used if a thumbnail or tunnel is unavailable. Old paths are removed when the current preview changes or no visible Onshape window is found.

Quick Tunnels need no Cloudflare account, but are intended for testing and development and have no uptime guarantee. Their hostname changes at app restart; the presence updates automatically. The helper launches silently at login and retries after exiting. This integration remains experimental.

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

## Development

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m py_compile main.py snapshot_bridge.py
```

The local instance guard uses port 19287; the image server uses port 19288. snapshot-status.json contains the current blurred preview URL and is ignored by Git. API calls have timeouts and metadata is cached for 60 seconds.

## Credits

Based on [IIRoan/OnshapeDRPC](https://github.com/IIRoan/OnshapeDRPC). This version adds selected-tab URL detection, blurred model previews, permission-enforced document links, silent startup helpers, reconnection, and diagnostics. Onshape and Discord are trademarks of their respective owners. This project is unofficial.

The upstream repository does not include a license file. This repository preserves attribution and does not add a license granting rights to upstream code.
