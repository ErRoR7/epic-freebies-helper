<div align="center">
  <h1>Epic Weekly Free Games Helper</h1>
  <p>An Epic weekly free-games claimer powered by GitHub Actions.</p>

  <p>
    <a href="https://github.com/Ronchy2000/epic-freebies-helper/actions/workflows/epic-gamer.yml"><img src="https://img.shields.io/github/actions/workflow/status/Ronchy2000/epic-freebies-helper/epic-gamer.yml?branch=master&style=flat-square" alt="Workflow Status" /></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square" alt="Python" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/Ronchy2000/epic-freebies-helper?style=flat-square" alt="License" /></a>
    <a href="https://github.com/Ronchy2000/epic-freebies-helper/stargazers"><img src="https://img.shields.io/github/stars/Ronchy2000/epic-freebies-helper?style=flat-square" alt="Stars" /></a>
    <a href="https://visitor-badge.laobi.icu/badge?page_id=Ronchy2000.epic-freebies-helper"><img src="https://visitor-badge.laobi.icu/badge?page_id=Ronchy2000.epic-freebies-helper&left_text=views" alt="Views" /></a>
  </p>
</div>

`Epic Weekly Free Games Helper` is built for regular users. It runs on GitHub Actions by default, so you do not need a server, a permanently running local machine, or any extra deployment. If you have a GitHub account, you can get started by following the setup steps below.

The key point is simple: in the common setup, you do not need to pay for a server or keep a local machine online. GitHub Actions is enough to run the weekly claim flow automatically. Captcha solving uses [NoneCap](https://nonecap.com), which includes free starter credits when you sign up.

The project is built upon community open-source solutions. Its core objective is to ensure the stability of auto-login, captcha solving, and checkout processes. hCaptcha challenges are solved with tokens bought from NoneCap: the automation reads the sitekey from the live challenge, requests a solved token, and injects it into the page — no LLM or image recognition is involved.

Community discussion and feedback are welcome on [LINUX DO](https://linux.do/t/topic/2036835/4).

If the project worked for you, feel free to leave a message here too: [🎉 Success Stories / Successful runs](https://github.com/Ronchy2000/epic-freebies-helper/discussions/3).

If you run into an error, please feel free to open an [Issue](https://github.com/Ronchy2000/epic-freebies-helper/issues). The choice is always yours, and I respect that; still, if you are willing to leave feedback instead of deleting the repo and walking away, those real reports and user experiences directly help improve the project and keep this effort moving forward.

---

## Feature Overview

| Feature | Description |
| --- | --- |
| Auto login | Signs in to your Epic account automatically |
| Weekly free games discovery | Fetches and identifies currently claimable free titles |
| Auto claim | Opens product pages and completes the checkout flow |
| Claim result notifications | Optionally sends a Telegram / WXPush (WeChat) run summary |
| Multi-account support | Optional; single-account behavior is unchanged when not configured |
| Captcha handling | Supports login captcha and checkout security checks |
| Scheduled execution | Runs once every Thursday by default on GitHub Actions and can be adjusted |

---

## Captcha Solving with NoneCap

hCaptcha solving is token-based via [NoneCap](https://nonecap.com):

- Minimal configuration: a single `NONECAP_API_KEY` Secret is all the solver needs.
- When a challenge appears, the automation submits the page's sitekey (and enterprise `rqdata` when present) to NoneCap and injects the returned token into the form.
- Failed solves are not charged, and new accounts start with free credits.
- Challenges that hCaptcha passes on its own (invisible, no interaction) are detected and treated as solved without spending a solve.
- Without a `NONECAP_API_KEY`, visible challenges cannot be solved and the login will fail whenever Epic serves one.

---

## Prerequisites

- Your Epic account email and password.
- Disable Epic email/SMS 2FA. Authenticator-app 2FA is supported when `EPIC_TOTP_SECRET` is configured.
- A NoneCap account with `NONECAP_API_KEY` prepared for captcha solving.

---

## 🚀 Quick Start

Basic configuration and execution steps:

### 1. Fork the repository and enable Actions

> [!TIP]
> If you have already forked this repository before, go to your fork on GitHub first and click `Sync fork` -> `Update branch` so your copy is aligned with the latest upstream changes before you continue.

After forking, open the `Actions` page in your fork, enter `Epic Awesome Gamer (Scheduled)`, and click `Enable workflow` once, or GitHub will not activate the scheduled run for that fork.

- Fork the repo to your own GitHub account.
- Open `Actions` and enable the workflow named `Epic Awesome Gamer (Scheduled)`.

### 2. Configure Secrets and Variables

Go to `Settings` -> `Secrets and variables` -> `Actions`.

Keep account credentials and API keys in `Secrets`. The captcha solver needs a single `NONECAP_API_KEY` Secret; there are no model settings anymore.

Required in all single-account setups (default path):

| Setting | Example value |
| --- | --- |
| `EPIC_EMAIL` | your_epic_email@example.com |
| `EPIC_PASSWORD` | your_epic_password |

If the Epic account uses authenticator-app 2FA, also configure:

| Setting | Example value |
| --- | --- |
| `EPIC_TOTP_SECRET` | The Base32 secret encoded in the authenticator QR code |

The workflow generates the current six-digit TOTP on the MFA page. Email codes, SMS codes, and Passkeys are not supported. Do not enter the currently displayed six-digit code as the Secret.

To receive Telegram claim summaries, optionally configure these Secrets:

| Setting | Example value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |

Both settings must be present before a notification is sent. The message includes run status, current weekly games, newly claimed games, previously owned games, unconfirmed items, and failure reasons. Telegram delivery failures do not affect the claim task; when these settings are absent, the existing behavior is preserved.

To also receive WXPush (WeChat template message) claim summaries, deploy your own [wxpush](https://github.com/frankiejun/wxpush) service first (Cloudflare Workers or Docker), then add these Secrets to the repository:

| Setting | Example value |
| --- | --- |
| `WXPUSH_ENDPOINT` | `https://your-worker.workers.dev` (service root is fine; `/wxsend` is appended automatically) |
| `WXPUSH_TOKEN` | The `API_TOKEN` you set when deploying wxpush |

Optional settings:

| Setting | Example value | Description |
| --- | --- | --- |
| `WXPUSH_USERID` | `OPENID1\|OPENID2` | Overrides the wxpush default recipients; when absent, wxpush's `WX_USERID` is used |
| `WXPUSH_TEMPLATE_ID` | Template ID | Overrides the wxpush default template; when absent, wxpush's `WX_TEMPLATE_ID` is used |
| `WXPUSH_BASE_URL` | `https://example.com/skin` | Tap-through URL for the template message; when absent, the wxpush `/skin` page is used to view the full content |

WXPush is independent from Telegram and both can be enabled at once. Because WeChat template title fields are limited (about 20 characters, no newlines), the WXPush title is a dense single-line summary carrying the key counts (for example `Epic:new2/7 total`, `Epic:new2 fail1` on partial failure, or `Epic failed:<reason>` on total failure); the content carries the full plain-text game list (run status, weekly games, newly claimed games, and so on). WeChat native popups usually show only the first ~20 characters of the content — tap the template message to open the wxpush `/skin` page for the complete list. If your WeChat template's content field is a strict type, an over-long body can fail the whole send (logged only, never affecting the claim task); Telegram remains available for the full summary. WXPush delivery failures do not affect the claim task; when these settings are absent, the existing behavior is preserved.

If shared cloud IP reputation causes unusually difficult hCaptcha challenges, you may optionally add a `BROWSER_PROXY` Secret. Supported forms are `http://username:password@host:port`, `https://...`, `socks4://...`, and `socks5://...`. Without it, browser networking is unchanged. Proxy quality, trust, and cost remain the user's responsibility.

For captcha solving, add the NoneCap key as a Secret:

| Setting | Example value |
| --- | --- |
| `NONECAP_API_KEY` | Your NoneCap API key |

Get a key from the [NoneCap dashboard](https://dashboard.nonecap.com). New accounts include free starter credits, and failed solves are not charged.

![GitHub Actions Secrets example](docs/images/tutorial/step2-actions-secrets.png)

### Multi-account support (optional)

This feature is fully optional. If you only configure `EPIC_EMAIL` / `EPIC_PASSWORD`, the existing single-account path is used unchanged.

If you have multiple Epic accounts, you can manage them all in a single Secret without forking the repo multiple times.

Go to `Settings` -> `Secrets and variables` -> `Actions` and create a new Secret:

| Setting | Example value |
| --- | --- |
| `EPIC_ACCOUNTS` | One account per line, format: `email:password` |

Example:

```text
user1@example.com:password1
user2@example.com:password2
user3@example.com:password3
```

Notes:

- If `EPIC_ACCOUNTS` is unset or empty, the exact legacy single-account path is used. There is no credential swapping and no aggregated exception wrapping.
- If `EPIC_ACCOUNTS` is set and **every non-empty line is valid**, the multi-account path runs sequentially.
- If `EPIC_ACCOUNTS` contains **no valid lines**, the job falls back only when both `EPIC_EMAIL` and `EPIC_PASSWORD` are configured. Otherwise, it fails with a configuration error before starting a browser with empty credentials.
- If `EPIC_ACCOUNTS` is set with **some valid and some invalid lines**, the job fails with a configuration error that lists the invalid line numbers. It will not silently skip bad lines and still report success.
- Email shape is lightly validated, including rejection of path separators and control characters. If a password contains a colon `:`, only the first colon is used as the separator.
- Each account runs independently: one account's failure does not affect the others. Each account still reuses the current login, hCaptcha, TOTP, Telegram, WXPush, and browser runtime path.
- Each account automatically gets its own isolated browser profile directory keyed by email.
- Multi-account Telegram / WXPush messages include a masked account label. Single-account formatting is unchanged when no label is supplied.
- `EPIC_TOTP_SECRET` remains a global setting for now. It fits a shared authenticator secret, or enabling TOTP for only one of the accounts. Per-account TOTP is not supported yet.
- Multiple accounts run sequentially in one job. Since a single account can take 15-20 minutes, raise the workflow timeout for multiple accounts (see below).

> [!IMPORTANT]
> The workflow `timeout-minutes` defaults to 60, which fits a single account with room to spare. For more accounts, set a repository variable `JOB_TIMEOUT_MINUTES` (Settings -> Secrets and variables -> Actions -> Variables) to roughly 20 minutes per account, or the job may be killed before all accounts finish.

### 3. Run the workflow manually once

- Open the `Actions` page.
- Select `Epic Awesome Gamer (Scheduled)`.
- Click `Run workflow`.

> [!IMPORTANT]
> **Note**: Due to Epic's risk-control mechanisms, the script may trigger multiple retries during captcha and checkout stages, which can extend the total runtime to 15-20 minutes. It is recommended not to interrupt the workflow manually while it is in progress.

### 4. Check the logs

When the run succeeds, the logs usually contain lines like:

```text
Login success
Right account validation success
Authentication completed
Starting free games collection process
All week-free games are already in the library
```

Example log with warnings but final success:

![Warnings but final success log example](docs/images/tutorial/step4-log-success-with-warnings-1.png)

If the logs show repeated retries and you cancel the run manually, like the example below, that still does not prove the automation had already failed. In many cases it simply had not finished yet:

![Do not cancel the Actions run too early](docs/images/faq/action-cancel-too-early.svg)

---

## Run Logs and Artifacts

Each GitHub Actions run attempts to upload the artifacts below. GitHub only shows artifacts that actually contain files, so different users may see only some of them. That is normal.

| Artifact | Content | When it usually appears |
| --- | --- |
| `epic-logs-<run_id>` | Runtime logs | Almost every run |
| `epic-runtime-<run_id>` | `promotions.json`, `purchase_debug` screenshots, and debug text | Common after the run reaches freebie discovery, product pages, or checkout |
| `epic-screenshots-<run_id>` | Extra screenshots for login failures, risk-control pages, and auth debugging | Only when the login, risk-control, or auth flow saved screenshots |

Download location:

1. Open the specific Actions run page.
2. Scroll to the bottom.
3. Find `Artifacts`.
4. Download the zip files.

What to inspect first:

| Package | What to inspect first |
| --- | --- |
| `epic-logs-<run_id>.zip` | After extraction, open the log files directly |
| `epic-runtime-<run_id>.zip` | If present, check the screenshots and debug text inside `purchase_debug/` first |
| `epic-screenshots-<run_id>.zip` | If present, check login, risk-control, or auth screenshots first |

These files are generated and uploaded after each GitHub Actions run. They are not fixed directories pre-shipped in the repository root.

If you need to open an issue, do not paste only a short log excerpt.

- If your fork is public, the Actions run URL is usually enough because maintainers can inspect the run page directly.
- If your fork is private, you must upload the artifact zip files that were actually generated for that run. Maintainers cannot access private Actions pages or private run artifacts.

---

## Local One-Shot Debugging

If you want to reproduce the same entrypoint locally, use the repository's built-in one-shot run path:

1. Copy [`.env.example`](.env.example) to `.env`
2. Fill in your own account and NoneCap configuration
3. Run `uv sync --group dev`
4. Run `ENABLE_APSCHEDULER=false uv run app/deploy.py`

`.env`, `.venv`, and `app/volumes/` are already ignored by `.gitignore`, so they will not be committed to GitHub.

> [!TIP]
> If your password or API key contains `$`, `\`, `#`, or `` ` ``, wrap the value in single quotes (e.g. `EPIC_PASSWORD='abc$def'`) so that `python-dotenv` does not treat `$xxx` as variable interpolation and silently drop characters. GitHub Actions Secrets are not affected.

---

## FAQ

### 1. Login randomly fails

**Cause**: GitHub Actions environments use shared cloud IPs, which easily trigger Epic's strict risk control, causing fluctuations in captcha success rates. This is an expected behavioral pattern.

### 2. Logs mention `privacy-policy correction` or the run gets stuck on a privacy-policy page

This is usually not a captcha-solver issue. It is an Epic account state issue. Some accounts are redirected after login to a page like `/id/login/correction/privacy-policy`, which requires a one-time privacy-policy confirmation.

The fix is simple: sign in to Epic once in a normal browser, complete that confirmation page manually, and then rerun the workflow.

### 3. Logs show `two_factor_authentication.required` or the page goes to `/id/login/mfa`

This means the Epic account entered its two-factor authentication flow. For authenticator-app 2FA, add `EPIC_TOTP_SECRET` to GitHub Secrets and the workflow will generate and submit the current six-digit TOTP. Email codes, SMS codes, and Passkeys are not supported.

If you see signals like these, treat them as “Epic requires 2FA verification”:

- `errors.com.epicgames.common.two_factor_authentication.required`
- `Two-Factor authentication required to process request`
- A redirect to `/id/login/mfa`

How to fix it:

1. Sign in to the Epic account in a normal browser
2. Open the account security settings page
3. For authenticator-app 2FA, add the QR code's Base32 secret to GitHub Secrets as `EPIC_TOTP_SECRET`
4. If you do not want automatic authenticator codes, click `Remove` for the enabled verification method
5. Rerun the workflow

Reference page:

![Epic 2FA remove methods](docs/images/faq/epic-2fa-remove-methods.png)

### 4. The page shows `One more step`

This is not automatically a bug. It is Epic's extra human-verification step during checkout.

**Description**: This is an additional security verification step during checkout. The workflow already contains automation logic for this stage, so seeing the prompt below does not automatically mean the script is broken.

![Checkout Security Check](docs/images/faq/checkout-security-check.png)

### 5. The page shows `Device not supported`

This usually happens when the product officially supports Windows while GitHub Actions is running on Linux.

By itself, this does not always mean the claim failed. The current automation will try to click `Continue` on that dialog and keep going.

### 6. Why can the workflow report success while the game is not in the library?

Historically, the common root causes were:

| Cause | Description |
| --- | --- |
| Product-page state recognition was inaccurate | The page copy and the real state did not match |
| `Place Order` was clicked but checkout was still incomplete | The checkout page was still blocked by a security check |
| Another popup interrupted the flow | For example `Device not supported` or an extra confirmation |
| Older logic misclassified page text | Some non-ownership text was previously misread as "already owned" |

---

## Docker Deployment

If you do not want to use GitHub Actions, you can also run the project on your own server, NAS, or local Docker environment.

### 1. Clone the repository

```bash
git clone https://github.com/Ronchy2000/epic-freebies-helper.git
cd epic-freebies-helper
```

### 2. Edit the configuration

The main entry is [`docker/docker-compose.yaml`](docker/docker-compose.yaml).

NoneCap example:

```yaml
environment:
  - NONECAP_API_KEY=your_nonecap_key
```

### 3. Start the stack

```bash
docker compose up -d --build
```

---

## Additional Documentation

If you want the project structure, adapter details, and developer-oriented troubleshooting notes, continue with:

- [Advanced Guide](docs/advanced.en.md)
- [GitHub Actions Guide](.github/workflows/README.md)
- [Development Log (2026-04-22)](docs/development-log-2026-04-22.en.md)
- [Maintenance Log](docs/maintenance-log.md)

---

## Project Origins and References

This project is based on `QIN2DIM/epic-awesome-gamer` and also references `10000ge10000/epic-kiosk`:

| Project | Description |
| --- | --- |
| [QIN2DIM/epic-awesome-gamer](https://github.com/QIN2DIM/epic-awesome-gamer) | Original project and source of the core automation ideas |
| [10000ge10000/epic-kiosk](https://github.com/10000ge10000/epic-kiosk) | Important reference for GitHub Actions packaging and documentation layout |
| [LINUX DO](https://linux.do/t/topic/2036835/4) | Community discussion, feedback, and project promotion support |

Thanks to the original authors, maintainers, and the community work that made this project possible.

---

## Disclaimer

- This project is for learning and research around automation flows.
- Automated actions may violate the target platform's terms of service. Evaluate the risk yourself.
- You are responsible for any consequences caused by using this project.

---

## Star History

<a href="https://www.star-history.com/#Ronchy2000/epic-freebies-helper&amp;Date">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="https://api.star-history.com/svg?repos=ronchy2000%2Fepic-freebies-helper&amp;type=Date&amp;theme=dark"
    />
    <source
      media="(prefers-color-scheme: light)"
      srcset="https://api.star-history.com/svg?repos=ronchy2000%2Fepic-freebies-helper&amp;type=Date"
    />
    <img
      alt="Star History Chart"
      src="https://api.star-history.com/svg?repos=ronchy2000%2Fepic-freebies-helper&amp;type=Date"
    />
  </picture>
</a>

---

## Community Thanks

The continuous improvement of this project relies not only on code iterations, but heavily on every user who, upon encountering an error, chose not to give up, but patiently submitted a complete error report.

The resolution of many edge cases did not stem from unilateral developer testing, but was built upon the detailed logs, screenshots, and reproduction steps actively provided by the community. It is this authentic diagnostic data that enabled obscure and hidden issues to be accurately isolated and resolved.

We extend our most genuine gratitude to everyone who has submitted feedback. The time you invested and the real-world data you shared have steadily illuminated the blind spots in development, allowing this project to mature and genuinely benefit a wider audience.

<div align="center">
  <sub>Thank you to everyone who opened issues, uploaded artifacts, and shared real failure cases.</sub>
</div>

<p align="center">
  <a href="https://github.com/AaronL725"><img src="https://github.com/AaronL725.png?size=96" width="64" height="64" alt="@AaronL725" /></a>
  <a href="https://github.com/cita-777"><img src="https://github.com/cita-777.png?size=96" width="64" height="64" alt="@cita-777" /></a>
  <a href="https://github.com/1208nn"><img src="https://github.com/1208nn.png?size=96" width="64" height="64" alt="@1208nn" /></a>
  <a href="https://github.com/LGDhuanghe"><img src="https://github.com/LGDhuanghe.png?size=96" width="64" height="64" alt="@LGDhuanghe" /></a>
  <a href="https://github.com/AdjieC"><img src="https://github.com/AdjieC.png?size=96" width="64" height="64" alt="@AdjieC" /></a>
  <a href="https://github.com/Leafrostar"><img src="https://github.com/Leafrostar.png?size=96" width="64" height="64" alt="@Leafrostar" /></a>
  <a href="https://github.com/AcosX"><img src="https://github.com/AcosX.png?size=96" width="64" height="64" alt="@AcosX" /></a>
  <a href="https://github.com/Elykia093"><img src="https://github.com/Elykia093.png?size=96" width="64" height="64" alt="@Elykia093" /></a>
  <a href="https://github.com/ZoveyOhhh"><img src="https://github.com/ZoveyOhhh.png?size=96" width="64" height="64" alt="@ZoveyOhhh" /></a>
</p>

<!-- <p align="center">
  <sub>
    <a href="https://github.com/AaronL725"><b>AaronL725</b></a> ·
    <a href="https://github.com/cita-777"><b>cita-777</b></a> ·
    <a href="https://github.com/1208nn"><b>1208nn</b></a> ·
    <a href="https://github.com/LGDhuanghe"><b>LGDhuanghe</b></a> ·
    <a href="https://github.com/AdjieC"><b>AdjieC</b></a> ·
    <a href="https://github.com/Leafrostar"><b>Leafrostar</b></a> ·
    <a href="https://github.com/AcosX"><b>AcosX</b></a> ·
    <a href="https://github.com/Elykia093"><b>Elykia093</b></a> ·
    <a href="https://github.com/ZoveyOhhh"><b>ZoveyOhhh</b></a>
  </sub>
</p> -->

<!--
Avatar wall template:

<p align="center">
  <a href="https://github.com/<username-1>"><img src="https://github.com/<username-1>.png?size=96" width="64" height="64" alt="@<username-1>" /></a>
  <a href="https://github.com/<username-2>"><img src="https://github.com/<username-2>.png?size=96" width="64" height="64" alt="@<username-2>" /></a>
  <a href="https://github.com/<username-3>"><img src="https://github.com/<username-3>.png?size=96" width="64" height="64" alt="@<username-3>" /></a>
</p>

<p align="center">
  <sub>
    <a href="https://github.com/<username-1>"><b><username-1></b></a> ·
    <a href="https://github.com/<username-2>"><b><username-2></b></a> ·
    <a href="https://github.com/<username-3>"><b><username-3></b></a>
  </sub>
</p>
-->
