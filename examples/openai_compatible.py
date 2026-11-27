#!/usr/bin/env python3
"""A minimal TAP agent for any OpenAI-compatible chat completions endpoint.

Configuration (environment variables):
    TAP_BASE_URL  base URL, for example https://api.example.com/v1
    TAP_API_KEY   bearer token for the endpoint
    TAP_MODEL     model name

Usage:
    TAP_BASE_URL=... TAP_API_KEY=... TAP_MODEL=... \\
        python3 openai_compatible.py "Summarize README.md"

Tools: read_file and shell. Before every shell command the script asks on stdin
(y/N); nothing runs unless you answer y. Requires the heurica_tap package
(pip install -e packages/python) or PYTHONPATH pointing at its src/.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

try:
    from heurica_tap import run_agent
except ImportError:  # run from a checkout without installing the package
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packages", "python", "src"))
    from heurica_tap import run_agent

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a text file in the project. Optional start and end lines (1-based).",
        "args": {
            "path": {"type": "string", "required": True, "description": "File path relative to the project"},
            "start": {"type": "integer"},
            "end": {"type": "integer"},
        },
        "readonly": True,
    },
    {
        "name": "shell",
        "description": "Run a shell command in the project folder. The user must approve each command.",
        "args": {
            "command": {"type": "string", "required": True},
            "timeout": {"type": "integer", "description": "Seconds before the command is stopped (default 60)"},
        },
    },
]


def read_file(args):
    path = args["path"]
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    start = int(args.get("start") or 1)
    end = int(args.get("end") or len(lines))
    chunk = lines[start - 1:end]
    return "\n".join(chunk) if chunk else "(empty)"


def shell(args):
    command = args["command"]
    timeout = int(args.get("timeout") or 60)
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    output = (proc.stdout or "") + (proc.stderr or "")
    status = "exit %d" % proc.returncode
    return {"ok": proc.returncode == 0, "output": "%s\n%s" % (status, output.strip())}


def approve(action):
    """Ask before any shell command. read_file runs without asking."""
    if action.tool != "shell":
        return True
    print("\nThe model wants to run: %s" % action.args.get("command", ""))
    answer = input("Run it? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def make_chat(base_url, api_key, model):
    url = base_url.rstrip("/") + "/chat/completions"

    def chat(messages, stop=None):
        body = {"model": model, "messages": messages, "temperature": 0}
        if stop:
            body["stop"] = list(stop)
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError("HTTP %d from %s: %s" % (exc.code, url, exc.read()[:500])) from exc
        return payload["choices"][0]["message"]["content"] or ""

    return chat


def main(argv):
    base_url = os.environ.get("TAP_BASE_URL", "")
    api_key = os.environ.get("TAP_API_KEY", "")
    model = os.environ.get("TAP_MODEL", "")
    if not (base_url and api_key and model):
        print("Set TAP_BASE_URL, TAP_API_KEY and TAP_MODEL.", file=sys.stderr)
        return 2
    task = " ".join(argv[1:]).strip()
    if not task:
        print("Usage: openai_compatible.py <task>", file=sys.stderr)
        return 2

    outcome = run_agent(
        chat=make_chat(base_url, api_key, model),
        tools=TOOLS,
        handlers={"read_file": read_file, "shell": shell},
        task=task,
        max_steps=20,
        approve=approve,
        instructions="Work in the project folder. Read before you edit, and verify before you say done.",
        name="a coding assistant",
    )
    print("\n" + (outcome.answer or "(no final answer after %d steps)" % outcome.steps))
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
