# OnshapeDRPC

Discord Rich Presence for Onshape on Windows, with automatic model previews and accurate labels for the tab you are viewing.

```text
Onshape
Part Studio: Intake
Document: Robot Design
[Model thumbnail with a small Onshape badge]
```

## Features

- Displays **Onshape** with your current document and selected tab.
- Identifies **Part Studio**, **Assembly**, **Drawing**, **Variable Studio**, **Bill of Materials**, and imported files.
- Reads the selected Onshape page URL through Windows accessibility, including installed Onshape browser apps. Duplicate tab names and non-default workspaces are resolved using their IDs.
- Replaces the large logo with the selected element's generated model thumbnail, while keeping the small Onshape badge.
- Updates tab selection every 15 seconds and checks for thumbnail changes every 90 seconds.
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

Setup creates a virtual environment, installs Python dependencies, creates `.env` if needed, and downloads the official `cloudflared` Windows executable. It requires a valid Windows signature identifying Cloudflare before completing setup.

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

Open Discord and an Onshape document. The selected tab should appear on your Discord profile within about 15 seconds. A new thumbnail tunnel can take longer to become available.

### Start automatically at login

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-startup.ps1
```

This installs `OnshapeDRPC.lnk` in your Windows Startup folder. It runs `venv\Scripts\pythonw.exe main.py` with this project as the working directory. Windows restart is handled when you next sign in.

To disable automatic startup, open `shell:startup` using Win + R and delete `OnshapeDRPC.lnk`. To stop a currently running instance, end the Python process belonging to this project in Task Manager. Re-running the launcher while an instance is running does not start a second copy.

## How snapshots work

Discord requires an externally accessible image URL. Private Onshape thumbnails require authentication, so a direct thumbnail link cannot be used by Discord.

1. The app reads the selected document, workspace/version, and element IDs.
2. It downloads the element's 300 x 300 PNG thumbnail using your existing Onshape credentials.
3. A local server bound to `127.0.0.1:19288` serves only the current thumbnail at a randomly generated image path.
4. A [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) provides a temporary HTTPS URL that Discord can fetch.
5. The image changes when you switch tabs and is checked for updates every 90 seconds. If no supported thumbnail is available, the Onshape logo is used.

**Your Onshape document remains private, but the displayed thumbnail is public to anyone who has its image URL.** Cloudflare and Discord process that image. The server exposes no API credentials, CAD files, filesystem browsing, or general-purpose API proxy. Unrecognized image paths return 404. Previous paths are removed when the current thumbnail changes or the app no longer finds an Onshape window; Discord may retain cached images.

Quick Tunnels do not require a Cloudflare account or domain. They are intended for testing and development, have no uptime guarantee, and receive a new hostname when restarted. The app updates the presence with the new URL and retries tunnel creation after the helper exits. This integration should be considered experimental.

The preview is Onshape's generated thumbnail, **not a capture of your exact viewport or current camera angle**. Sketches and some element types may have no suitable thumbnail.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No presence | Open the Discord desktop app and an Onshape window; inspect `presence.log`. |
| Logo remains | Allow time for the tunnel to connect; confirm the selected element has a PNG thumbnail and Cloudflare is reachable. |
| Generic `Tab` label | The selected page URL was unavailable and the window title matched duplicate element names. |
| Wrong window | With multiple Onshape windows, the foremost visible Onshape window is used. Background tabs inside another browser window are not monitored. |
| Document is not found | Verify API access. URL detection is preferable; title fallback only uses the default workspace and refuses duplicate document names. |
| Startup fails | Keep the project in the same location and rerun `setup.ps1` and `install-startup.ps1` after moving it. |
| Display name differs | The app requests `Onshape`; Discord behavior can depend on the configured Rich Presence application. |

For visible debugging:

```powershell
.\venv\Scripts\python.exe main.py
```

Do not run this alongside an existing background instance. `presence.log` rotates at 500 KB with two backups. `snapshot-status.json` contains the current local diagnostic image URL. Both are ignored by Git.

## Development

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m py_compile main.py snapshot_bridge.py
```

The local instance guard uses port 19287; the thumbnail server uses port 19288. API calls have timeouts and metadata is cached for 60 seconds.

## Credits

Based on [IIRoan/OnshapeDRPC](https://github.com/IIRoan/OnshapeDRPC). This version adds selected-tab URL detection, automatic thumbnail serving, silent startup helpers, reconnection, and diagnostics. Onshape and Discord are trademarks of their respective owners. This project is unofficial.

The upstream repository does not include a license file. This repository preserves attribution and does not add a license granting rights to upstream code.
