# Cadence

**Mark a moment. Get the rhythm.**

Cadence is a tiny self-hosted vide-coded web app. Press one button to record the current time
(**X**), and it lays out a schedule of repeating times (**X + N hours**, **X + 2N hours**, …)
across the next 24 hours, with an alarm for each one. It is useful for anything that
repeats on a fixed interval: medication, feeding, watering, breaks, timers, checks.

It runs on a PC and you use it from any browser on your network, such as your phone.
Python only, no packages to install, no cloud, no account.

## Features

- **One-tap recording.** The big button saves the current time as X.
- **Your interval.** Choose N from 0.5 to 24 hours (default 3). Use the − / + buttons or type a value such as 2.25.
- **Daily schedule.** Shows X+N, X+2N, … covering 24 hours, with the date where it crosses midnight.
- **Alarms.** Toggle an alarm on any time: a loud beep, vibration and a full-screen Stop button.
- **Android clock alarms.** Android Chrome also gets a **Phone alarm** button that adds the time to your clock app.
- **Notes.** Add a note to each recorded time. It saves automatically.
- **History.** Every recorded time and note is kept on the PC in `cadence_data.json`. Tap an entry to reopen its schedule.
- **Clear history.** **Remove** (per entry) and **Clear history** (all) hide entries from the page but never delete them from disk. Cleared entries are marked `"cleared"` in the JSON file; delete that field to bring one back.
- **CSV export.** Download all history from the page (`/export.csv`), including cleared entries (marked in the last column).
- **Mobile friendly.** Large touch targets, safe-area aware, dark mode, and "Add to Home Screen" support.
- **http and https on one port.** The same address works both ways.

## Quick start

1. Install Python 3.6 or newer.
2. Put `cadence.py` and `cadence.html` in the same folder.
3. Run:

   ```
   python cadence.py
   ```

4. The script prints the addresses to open, for example:

   ```
   http://192.168.1.23:8000
   https://192.168.1.23:8000
   ```

5. Open one on your phone or any PC on the same network. Press **Record time now**.

To use another port: `python cadence.py 8080`.

## Files

| File | Purpose |
| --- | --- |
| `cadence.py` | The server: serves the page, stores data, handles http and https |
| `cadence.html` | The web page (HTML, CSS and JavaScript in one file) |
| `cadence_data.json` | Your recorded times and notes (created on first use) |
| `cadence_cert.pem`, `cadence_key.pem`, `cadence_cert.ip` | Self-signed https certificate (created on first start) |

The server re-reads `cadence.html` on every request, so after editing the page you only need to refresh the browser.

## Alarms: what to expect

A web page cannot ring while it is closed or the phone is asleep.

- **Set alarm** rings inside the open page, so keep it open with the screen on. Over https the browser can also keep the screen awake while alarms are set.
- **Phone alarm** (Android Chrome) creates a real alarm in your clock app, which rings reliably.
- Alarms are stored per device, in the browser where you set them. Changing the interval or deleting an entry clears the alarms for it.

## https

Cadence also answers `https://` on the same port. On first start it creates a self-signed
certificate, which needs either the `openssl` command or `pip install cryptography`.
If neither is available, it runs on http only and says so at startup.

Browsers do not trust a self-signed certificate, so they show a one-time warning:
choose **Advanced**, then **Proceed**. On a home network, http is perfectly fine.

## Troubleshooting

**Works on the host PC but not from other devices.** Almost always the firewall on the host.

- Windows (Command Prompt as Administrator):
  `netsh advfirewall firewall add rule name="Cadence" dir=in action=allow protocol=TCP localport=8000`
- Linux with ufw: `sudo ufw allow 8000/tcp`

Also check that you are using the PC's real LAN IP (`ipconfig` or `ip a`), that both devices are
on the same network (not guest Wi-Fi or an isolated network), and that the script is not running
inside WSL2 or a container.

**Port already in use.** The script tells you. Pick another port: `python cadence.py 8080`.

**Running next to Pi-hole.** Pi-hole's admin page uses ports 80 and 443, so the default port 8000 does not clash.
Use the IP address rather than a made-up host name unless you add a Local DNS record in Pi-hole.

**The IP address changed.** Give the PC a fixed address (DHCP reservation) in your router.
Cadence makes a new certificate automatically when the IP changes.

## Privacy and security

Everything stays on your PC and your network. There is no login, so anyone who can reach the
address can see and edit your data: use it on a trusted home network, and do not expose the port to the internet.

## Customising

All the look and behaviour of the page is in `cadence.html`. Useful spots:

- `DEF_H` sets the default interval, and `MAX_SLOTS` caps the number of times shown.
- The colours are CSS variables at the top of the `<style>` block, with a dark-mode set below them.
- The server port and file locations are at the top of `cadence.py`.
