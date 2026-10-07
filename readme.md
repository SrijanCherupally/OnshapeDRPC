# OnshapeDRPC

Discord Rich Presence for Onshape on Windows, with accurate labels for the tab you are viewing.

```text
Onshape
Part Studio: Intake
Document: Robot Design
[Onshape logo]
```

## Features

- Displays **Onshape** with your current document and selected tab.
- Identifies **Part Studio**, **Assembly**, **Drawing**, **Variable Studio**, **Bill of Materials**, and imported files.
- Reads the selected Onshape page URL through Windows accessibility, including installed Onshape browser apps. Duplicate tab names and non-default workspaces are resolved using their IDs.
- Uses the Onshape logo and provides a **View in Onshape** button; document access is enforced by Onshape.
- Updates tab selection every 15 seconds.
- Runs silently, starts at Windows login, reconnects when Discord becomes available, and prevents duplicate instances.
- Keeps rotating local diagnostic logs instead of requiring a console window.

## Requirements

- Windows 10 or 11 on an x64 computer.
- Python 3.10 or newer, available as `python` on PATH.
- The Discord desktop application.
- An Onshape account and API access/secret keys with permission to read the relevant documents.
- Brave, Chrome, Edge, or Firefox. URL detection is verified with Brave's installed Onshape app; support depends on the browser exposing the selected page through Windows accessibility.
- Internet access to Onshape and Discord.

## Install

Open PowerShell in the folder where you want to keep the application:

```powershell
git clone https://github.com/SrijanCherupally/OnshapeDRPC.git
cd OnshapeDRPC
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup creates a virtual environment, installs Python dependencies, and creates `.env` if needed.

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

## Document Privacy

Discord Rich Presence images cannot enforce Onshape permissions for each viewer. External images must be publicly accessible to Discord, and the Rich Presence API cannot authenticate viewers against your document access list.

This version therefore displays the Onshape logo, fetches no model thumbnails, and runs no public image server or tunnel. The **View in Onshape** button opens the exact document tab; Onshape requires sign-in and enforces the document's permissions there. Document and tab names are still shown to anyone who can view your Discord activity.

An earlier revision used public thumbnail URLs through Cloudflare. That feature has been removed. Existing users should stop any previously running app and project-specific cloudflared process before updating and restarting. Previously displayed images may remain in Discord caches; this app cannot revoke those cached copies.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No presence | Open the Discord desktop app and an Onshape window; inspect `presence.log`. |
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
.\venv\Scripts\python.exe -m py_compile main.py
```

The local instance guard uses port 19287. API calls have timeouts and metadata is cached for 60 seconds.

## Credits

Based on [IIRoan/OnshapeDRPC](https://github.com/IIRoan/OnshapeDRPC). This version adds selected-tab URL detection, permission-enforced document links, silent startup helpers, reconnection, and diagnostics. Onshape and Discord are trademarks of their respective owners. This project is unofficial.

The upstream repository does not include a license file. This repository preserves attribution and does not add a license granting rights to upstream code.
