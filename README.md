# Claude Code Cache Fix

Patch + test toolkit for the known Claude Code cache issues:
- resume cache regression (`deferred_tools_delta` / `mcp_instructions_delta`)
- write-heavy cache regression in `2.1.89+` (single tail cache marker)
- sentinel replacement behavior (`cch=00000`)

This repo keeps stock `claude` untouched and gives you a separate `claude-patched` command.
Installers currently pin `@anthropic-ai/claude-code@2.1.90`.

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

All three installers use `patches/apply-patches.py` which has regex and semantic search fallbacks for reliable patching across different minified code versions. Installers are version-aware — they detect when the installed version already matches the target and skip redundant work.

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

Four patches are applied to `cli.js`:

1. **db8 attachment filter** — persists `deferred_tools_delta` and `mcp_instructions_delta` attachments in the session JSONL so the cache prefix is reconstructed correctly on resume.
2. **Fingerprint meta skip** — ensures the first-message hash used in the attribution header ignores injected meta messages, keeping the cache key stable across turns.
3. **Rolling cache markers** — restores the older “last few messages” cache-marking behavior on `2.1.89+` instead of marking only a single tail message.
4. **Force 1h cache TTL** — bypasses the subscription/feature-flag check so all cache markers use 1-hour TTL instead of the default 5 minutes.

Each patch uses a 3-tier strategy: exact string match, regex fallback, then semantic/contextual search. The patchers also detect newer builds where a fix is already present and skip gracefully.

## Test Classifications

`test_cache.py` classifies resume cache behavior as one of:

| Status | Meaning |
|--------|---------|
| **healthy** | Read ratio ≥65%, strong cache reuse |
| **degraded** | Read ratio ≥40%, partial reuse |
| **write_heavy** | High creation volume despite some reads (2.1.89+ regression signature) |
| **broken** | Zero reads, all cache creation |
| **inconclusive** | API errors or insufficient data |

## Notes

- Requires `node`, `npm`, and `python3`.
- Requires Claude auth (`ANTHROPIC_API_KEY` or Claude local auth setup).
- A currently running old `claude-patched` process will not auto-update; start a new session after patching.
- Stock `claude` is never modified. To undo, just stop using `claude-patched`.
