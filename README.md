# Claude Code Cache Fix

Patch + test toolkit for the known Claude Code cache issues:
- resume cache regression (`deferred_tools_delta` / `mcp_instructions_delta`)
- sentinel replacement behavior (`cch=00000`)

This repo keeps stock `claude` untouched and gives you a separate `claude-patched` command.

## Quick Start

### Linux

```bash
./install.sh
```

### macOS

```bash
./install-mac.sh
```

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

Both Linux and macOS installers use `patches/apply-patches.py` which has regex and semantic search fallbacks for reliable patching across different minified code versions.

Then open a new terminal and verify.

Linux/macOS:

```bash
type -a claude-patched
python3 test_cache.py claude-patched --timeout 240 --debug-transcript
```

Windows (PowerShell):

```powershell
Get-Command claude-patched -All
python .\test_cache.py claude-patched --timeout 240 --debug-transcript
```

## First Run: Cold Cache Note

The first `test_cache.py` run after patching may report resume cache as "broken".
This is expected. The old 5-minute TTL cache entries from before the patch need to
expire before the new 1-hour TTL entries take effect. Run the test a second time
and it should report "healthy" with a read ratio of ~65-70%.

## Smoke Check (installer + test + summary)

Run:

```bash
./smoke_check.sh --timeout 240
```

What it does:
- runs installer (`install.sh` by default)
- runs `test_cache.py`
- saves full output under `results/`
- prints a short PASS/FAIL block you can paste into a post

For macOS, use:

```bash
./smoke_check.sh --installer ./install-mac.sh --timeout 240
```

## Usage Audit (real sessions)

To audit recent session cache efficiency:

```bash
python3 usage_audit.py --top 10 --window 8
```

Healthy sessions usually show high read ratio in the recent window.

## What the Patches Do

Three patches are applied to `cli.js`:

1. **db8 attachment filter** — persists `deferred_tools_delta` and `mcp_instructions_delta` attachments in the session JSONL so the cache prefix is reconstructed correctly on resume.
2. **Fingerprint meta skip** — ensures the first-message hash used in the attribution header ignores injected meta messages, keeping the cache key stable across turns.
3. **Force 1h cache TTL** — bypasses the subscription/feature-flag check so all cache markers use 1-hour TTL instead of the default 5 minutes.

## Notes

- Requires `node`, `npm`, and `python3`.
- Requires Claude auth (`ANTHROPIC_API_KEY` or Claude local auth setup).
- A currently running old `claude-patched` process will not auto-update; start a new session after patching.
- Stock `claude` is never modified. To undo, just stop using `claude-patched`.
