#!/usr/bin/env python3
"""
apply-patches.py — Patch Claude Code cli.js to fix cache bugs.

Patch 1: Modify db8 JSONL write filter to persist deferred_tools_delta and
         mcp_instructions_delta attachments. Fixes resume cache regression.

Patch 1c: Move the single transcript cache marker earlier on 2.1.89+ so the
          cached prefix remains reusable without exceeding the API limit.

Patch 2: Force 1-hour cache TTL on all cache_control markers. The API may
         ignore this if your plan doesn't support it, but it costs nothing to try.

Usage:
    python3 apply-patches.py /path/to/cli.js
"""

import re
import sys

# ── Patch definitions ────────────────────────────────────────────────────────

# Original db8: drops all attachment-type messages except hook_additional_context
DB8_ORIGINAL = (
    'function db8(A){'
    'if(A.type==="attachment"&&ss1()!=="ant"){'
    'if(A.attachment.type==="hook_additional_context"'
    '&&a6(process.env.CLAUDE_CODE_SAVE_HOOK_ADDITIONAL_CONTEXT))return!0;'
    'return!1}'
    'if(A.type==="progress"&&Ns6(A.data?.type))return!1;'
    'return!0}'
)

# Patched db8: also allows deferred_tools_delta and mcp_instructions_delta
DB8_PATCHED = (
    'function db8(A){'
    'if(A.type==="attachment"&&ss1()!=="ant"){'
    'if(A.attachment.type==="hook_additional_context"'
    '&&a6(process.env.CLAUDE_CODE_SAVE_HOOK_ADDITIONAL_CONTEXT))return!0;'
    'if(A.attachment.type==="deferred_tools_delta")return!0;'
    'if(A.attachment.type==="mcp_instructions_delta")return!0;'
    'return!1}'
    'if(A.type==="progress"&&Ns6(A.data?.type))return!1;'
    'return!0}'
)

NEW_ATTACHMENT_FILTER = re.compile(
    r'if\(\w+\.type==="attachment"&&\w+\(\)!=="ant"\)\{'
    r'if\(\w+\.attachment\.type==="hook_additional_context".*?'
    r'if\(\w+\.attachment\.type==="hook_deferred_tool"\)return!0;'
    r'return!1\}'
)
ATTACHMENT_FILTER_WITH_CACHE_ATTACHMENTS = re.compile(
    r'if\(\w+\.type==="attachment"&&\w+\(\)!=="ant"\)\{'
    r'(?:(?!return!1\}).)*\w+\.attachment\.type==="deferred_tools_delta"'
    r'(?:(?!return!1\}).)*\w+\.attachment\.type==="mcp_instructions_delta"'
    r'(?:(?!return!1\}).)*return!1\}'
)

# Original fingerprint selector: first user message, including meta messages
FINGERPRINT_ORIGINAL = 'function FA9(A){let q=A.find((_)=>_.type==="user");'
FINGERPRINT_PATCHED = (
    'function FA9(A){let q=A.find((_)=>_.type==="user"&&!("isMeta"in _&&_.isMeta));'
)
FINGERPRINT_PATCHED_REGEX = re.compile(
    r'function \w+\(\w+\)\{let \w+=\w+\.find\(\((\w+)\)=>\1\.type==="user"&&!\("isMeta"in \1&&\1\.isMeta\)\);'
)

SINGLE_MARKER_ORIGINAL = (
    "let A=O?q.length-2:q.length-1,"
    "w=q.map((J,M)=>{let X=M===A;"
    'if(J.type==="user")return jxY(J,X,K,_);'
    "return HxY(J,X,K,_)})"
)
SINGLE_MARKER_PATCHED = (
    "let A=O?q.length-2:q.length-2,"
    "w=q.map((J,M)=>{let X=M===A;"
    'if(J.type==="user")return jxY(J,X,K,_);'
    "return HxY(J,X,K,_)})"
)
ROLLING_MARKER_PATCHED_REGEX = re.compile(
    r'let \w+=\w+\?\w+\.length-2:\w+\.length-2,'
    r'\w+=\w+\.map\(\(\w+,\w+\)=>\{let \w+=.*?;'
    r'if\(\w+\.type==="user"\)return \w+\(\w+,\w+,\w+,\w+\);'
    r'return \w+\(\w+,\w+,\w+,\w+\)\}\)'
)
ANY_CACHE_MARKER_REGEX = re.compile(
    r"let (?P<target>\w+)=(?P<skip>\w+)\?(?P<arr>\w+)\.length-2:(?P=arr)\.length-1,"
    r"(?P<mapped>\w+)=(?P=arr)\.map\(\((?P<item>\w+),(?P<idx>\w+)\)=>\{"
    r"let (?P<flag>\w+)=(?:(?P=idx)===(?P=target)|"
    r"(?P=skip)\?(?P=idx)>=(?P=arr)\.length-\d+&&(?P=idx)<(?P=arr)\.length-1:"
    r"(?P=idx)>(?P=arr)\.length-\d+);"
)


def apply_patches(path: str) -> None:
    print(f"[*] Reading {path} ({''})...")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    print(f"    {len(source):,} bytes")
    patch1_not_needed = False

    # ── Patch 1: db8 attachment filter ────────────────────────────────────
    if DB8_PATCHED in source:
        print("[*] Patch 1 (db8 attachment filter): already applied, skipping")
    elif ATTACHMENT_FILTER_WITH_CACHE_ATTACHMENTS.search(source):
        patch1_not_needed = True
        print("[*] Patch 1 (db8 attachment filter): already present in this build, skipping")
    elif NEW_ATTACHMENT_FILTER.search(source):
        patch1_not_needed = True
        print("[*] Patch 1 (db8 attachment filter): not needed on this build, skipping")
    elif DB8_ORIGINAL in source:
        source = source.replace(DB8_ORIGINAL, DB8_PATCHED, 1)
        print("[*] Patch 1 (db8 attachment filter): applied")
    else:
        # Try generic regex fallback for newer minified bundles.
        pattern = re.compile(
            r'(function \w+\(\w+\)\{if\(\w+\.type==="attachment"&&\w+\(\)!=="ant"\)\{'
            r'if\(\w+\.attachment\.type==="hook_additional_context"'
            r'&&\w+\(process\.env\.\w+\)\)return!0;)'
            r'(return!1\})'
        )
        match = pattern.search(source)
        if match:
            func_match = re.match(r'function \w+\((\w+)\)', match.group(0))
            var = func_match.group(1) if func_match else "A"
            insert = (
                f'if({var}.attachment.type==="deferred_tools_delta")return!0;'
                f'if({var}.attachment.type==="mcp_instructions_delta")return!0;'
            )
            source = source[:match.start(2)] + insert + source[match.start(2):]
            print("[*] Patch 1 (db8 attachment filter): applied via regex fallback")
        else:
            idx = source.find('"hook_additional_context"')
            if idx != -1:
                region = source[idx:idx + 300]
                ret_match = re.search(r'return!1\}', region)
                if ret_match:
                    abs_pos = idx + ret_match.start()
                    var_match = re.search(
                        r'if\((\w+)\.attachment\.type==="hook',
                        source[max(0, idx - 50):idx + 50],
                    )
                    var = var_match.group(1) if var_match else "A"
                    insert = (
                        f'if({var}.attachment.type==="deferred_tools_delta")return!0;'
                        f'if({var}.attachment.type==="mcp_instructions_delta")return!0;'
                    )
                    source = source[:abs_pos] + insert + source[abs_pos:]
                    print("[*] Patch 1 (db8 attachment filter): applied via semantic fallback")
                else:
                    print("[!] Patch 1 FAILED: found hook_additional_context but no insertion point")
                    sys.exit(1)
            else:
                print("[!] Patch 1 FAILED: could not find attachment filter")
                print("    Expected pattern not found. Has cli.js been updated?")
                sys.exit(1)

    # ── Patch 1b: fingerprint source should ignore meta user messages ───────
    # Source equivalent:
    # extractFirstMessageText(messages.find(msg => msg.type==='user' && !msg.isMeta))
    if FINGERPRINT_PATCHED in source:
        print("[*] Patch 1b (fingerprint meta skip): already applied, skipping")
    elif FINGERPRINT_ORIGINAL in source:
        source = source.replace(FINGERPRINT_ORIGINAL, FINGERPRINT_PATCHED, 1)
        print("[*] Patch 1b (fingerprint meta skip): applied")
    else:
        # Regex fallback for different minifier variable names
        pattern = re.compile(
            r'function \w+\(\w+\)\{let \w+=\w+\.find\(\((\w+)\)=>\1\.type==="user"\);'
        )
        match = pattern.search(source)
        if match:
            var = match.group(1)
            old = match.group(0)
            new = old.replace(
                f'{var}.type==="user"',
                f'{var}.type==="user"&&!('
                f'"isMeta"in {var}&&{var}.isMeta'
                f')',
                1,
            )
            source = source[:match.start()] + new + source[match.end():]
            print("[*] Patch 1b (fingerprint meta skip): applied via regex fallback")
        else:
            print("[!] Patch 1b WARNING: could not find fingerprint selector, skipping")
            print("    Non-critical; resume first-turn cache may still miss.")

    # ── Patch 1c: move the single cache marker earlier on 2.1.89+ ─────────
    if SINGLE_MARKER_PATCHED in source:
        print("[*] Patch 1c (earlier cache marker): already applied, skipping")
    elif SINGLE_MARKER_ORIGINAL in source:
        source = source.replace(SINGLE_MARKER_ORIGINAL, SINGLE_MARKER_PATCHED, 1)
        print("[*] Patch 1c (earlier cache marker): applied")
    else:
        match = ANY_CACHE_MARKER_REGEX.search(source)
        if match:
            g = match.groupdict()
            replacement = (
                f"let {g['target']}={g['skip']}?{g['arr']}.length-2:{g['arr']}.length-2,"
                f"{g['mapped']}={g['arr']}.map(({g['item']},{g['idx']})=>{{"
                f"let {g['flag']}={g['idx']}==={g['target']};"
            )
            source = source[:match.start()] + replacement + source[match.end():]
            print("[*] Patch 1c (earlier cache marker): applied via regex fallback")
        else:
            print("[*] Patch 1c (earlier cache marker): not needed or pattern not found, skipping")

    # ── Patch 2: Force 1-hour cache TTL ─────────────────────────────────
    # sjY() gates whether cache_control gets ttl:"1h". It checks subscription
    # status and a server-side feature flag allowlist. We bypass all of that.
    # If the API doesn't support 1h for your plan, it silently ignores it.
    SJY_ORIGINAL = 'function sjY(A){if(QA()==="bedrock"'
    SJY_PATCHED = 'function sjY(A){return!0;if(QA()==="bedrock"'

    if SJY_PATCHED in source:
        print("[*] Patch 2 (force 1h cache TTL): already applied, skipping")
    elif SJY_ORIGINAL in source:
        source = source.replace(SJY_ORIGINAL, SJY_PATCHED, 1)
        print("[*] Patch 2 (force 1h cache TTL): applied")
    else:
        pattern = re.compile(
            r'(function \w+\(\w+\)\{)'
            r'(if\(\w+\(\)==="bedrock"&&\w+\(process\.env\.ENABLE_PROMPT_CACHING_1H_BEDROCK\))'
        )
        match = pattern.search(source)
        if match:
            source = source[:match.end(1)] + "return!0;" + source[match.end(1):]
            print("[*] Patch 2 (force 1h cache TTL): applied via regex fallback")
        else:
            exact_new = 'function OxY(q){if(T7()==="bedrock"'
            if exact_new in source:
                source = source.replace(exact_new, 'function OxY(q){return!0;if(T7()==="bedrock"', 1)
                print("[*] Patch 2 (force 1h cache TTL): applied via exact new-match")
            else:
                idx = source.find("ENABLE_PROMPT_CACHING_1H_BEDROCK")
                if idx != -1:
                    region = source[max(0, idx - 300):idx]
                    func_match = list(re.finditer(r'function \w+\(\w+\)\{', region))
                    if func_match:
                        last = func_match[-1]
                        abs_pos = max(0, idx - 300) + last.end()
                        source = source[:abs_pos] + "return!0;" + source[abs_pos:]
                        print("[*] Patch 2 (force 1h cache TTL): applied via semantic fallback")
                    else:
                        print("[!] Patch 2 WARNING: found 1h gate but no function boundary, skipping")
                        print("    1h cache TTL not forced. Non-critical, continuing.")
                else:
                    print("[!] Patch 2 WARNING: could not find sjY function, skipping")
                    print("    1h cache TTL not forced. Non-critical, continuing.")

    # ── Write back ────────────────────────────────────────────────────────
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    print(f"[*] Wrote patched file ({len(source):,} bytes)")

    # ── Verify ────────────────────────────────────────────────────────────
    with open(path, "r", encoding="utf-8") as f:
        verify = f.read()

    ok = True
    if DB8_PATCHED in verify:
        print("[*] Verification: Patch 1 (db8) confirmed")
    elif patch1_not_needed and (
        NEW_ATTACHMENT_FILTER.search(verify)
        or ATTACHMENT_FILTER_WITH_CACHE_ATTACHMENTS.search(verify)
    ):
        print("[*] Verification: Patch 1 skipped (new attachment filter build)")
    else:
        print("[!] Verification FAILED: Patch 1 (db8) not found in output")
        ok = False

    if FINGERPRINT_PATCHED in verify:
        print("[*] Verification: Patch 1b (fingerprint meta skip) confirmed")
    elif FINGERPRINT_PATCHED_REGEX.search(verify):
        print("[*] Verification: Patch 1b (fingerprint meta skip) confirmed")
    elif FINGERPRINT_ORIGINAL not in verify:
        print("[*] Verification: Patch 1b skipped (pattern not found)")
    else:
        print("[!] Verification FAILED: Patch 1b (fingerprint meta skip) not applied")
        ok = False

    if SINGLE_MARKER_PATCHED in verify:
        print("[*] Verification: Patch 1c (earlier cache marker) confirmed")
    elif ROLLING_MARKER_PATCHED_REGEX.search(verify):
        print("[*] Verification: Patch 1c (earlier cache marker) confirmed")
    elif SINGLE_MARKER_ORIGINAL not in verify:
        print("[*] Verification: Patch 1c skipped (pattern not found)")
    else:
        print("[!] Verification FAILED: Patch 1c (earlier cache marker) not applied")
        ok = False

    if SJY_PATCHED in verify:
        print("[*] Verification: Patch 2 (1h TTL) confirmed")
    elif re.search(
        r'function \w+\(\w+\)\{return!0;if\(\w+\(\)==="bedrock"&&\w+\(process\.env\.ENABLE_PROMPT_CACHING_1H_BEDROCK\)',
        verify,
    ):
        print("[*] Verification: Patch 2 (1h TTL) confirmed")
    elif SJY_ORIGINAL not in verify:
        print("[*] Verification: Patch 2 skipped (sjY not found)")
    else:
        print("[!] Verification FAILED: Patch 2 (1h TTL) not applied")
        ok = False

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-cli.js>")
        sys.exit(1)
    apply_patches(sys.argv[1])
