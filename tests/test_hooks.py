"""Wiring tests for the Grok/Claude hook stdin adapter.

Empty stdin used to raise JSONDecodeError and exit 1. That was the consistent
pre_tool_use / post_tool_use error. These tests run the real hook scripts.
"""

import json
import os
import subprocess
import sys

HOOKS = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks")


def _run(script, payload):
    path = os.path.join(HOOKS, script)
    if payload is None:
        raw = b""
    elif isinstance(payload, bytes):
        raw = payload
    else:
        raw = json.dumps(payload).encode("utf-8")
    proc = subprocess.run(
        [sys.executable, path],
        input=raw,
        capture_output=True,
        timeout=10,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def test_empty_stdin_fails_open():
    for script in (
        "no_emoji.py",
        "no_stubs.py",
        "protect_rules.py",
        "api_error_handling.py",
        "no_secrets_git.py",
        "remind_docs.py",
        "check_success_claims.py",
    ):
        code, err = _run(script, None)
        assert code == 0, f"{script} empty stdin exited {code}: {err}"


def test_grok_camelcase_payload_is_accepted():
    payload = {
        "hookEventName": "pre_tool_use",
        "toolName": "search_replace",
        "toolInput": {
            "filePath": "src/bleachmark/cli.py",
            "newString": "def hello():\n    return 1\n",
        },
    }
    code, err = _run("no_emoji.py", payload)
    assert code == 0, err
    code, err = _run("no_stubs.py", payload)
    assert code == 0, err


def test_git_add_all_still_blocked():
    payload = {
        "toolInput": {"command": "git add -A"},
        "toolName": "run_terminal_command",
    }
    code, err = _run("no_secrets_git.py", payload)
    assert code == 2
    assert "RULE 4" in err


def test_fixture_path_skips_emoji_hook():
    payload = {
        "tool_input": {
            "file_path": "tests/fixtures/carrier_corpus.py",
            "new_string": "zwsp = '\\u200d'\n",
        }
    }
    # the source contains a joiner escape, not a literal, so even without the
    # skip this would pass; the skip is for a literal carrier write
    code, err = _run("no_emoji.py", payload)
    assert code == 0, err
