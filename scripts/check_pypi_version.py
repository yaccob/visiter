#!/usr/bin/env python3
"""Refuse to publish if the local version already exists on PyPI.

Reads the project version from `visiter.__version__`, queries PyPI's
JSON API for the existing releases, and exits non-zero (with a clear
message) when a version conflict is detected. Run as a prerequisite
of `make publish` and `make test-publish`.

Network failures (DNS, timeout, 5xx) are treated as "cannot verify";
the script then errors so that no upload happens silently against a
stale assumption. Pass `--allow-network-failure` to downgrade that to
a warning if you need to publish in a network-restricted environment.

Usage:
    python scripts/check_pypi_version.py [--repository pypi|testpypi]
                                         [--allow-network-failure]
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

REPOSITORIES = {
    "pypi":     "https://pypi.org/pypi/{name}/json",
    "testpypi": "https://test.pypi.org/pypi/{name}/json",
}


def fetch_existing_versions(repository, package):
    url = REPOSITORIES[repository].format(name=package)
    with urllib.request.urlopen(url, timeout=10) as resp:
        payload = json.load(resp)
    return set(payload.get("releases", {}).keys())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", choices=REPOSITORIES, default="pypi")
    parser.add_argument("--allow-network-failure", action="store_true")
    args = parser.parse_args()

    from visiter import __version__ as local_version
    package = "visiter"

    try:
        existing = fetch_existing_versions(args.repository, package)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Package not yet on this index — first release is fine.
            print(f"OK: {package} not on {args.repository}; "
                  f"first release of {local_version} will succeed.")
            return 0
        msg = f"could not query {args.repository} ({e}); refusing to publish"
        if args.allow_network_failure:
            print(f"WARNING: {msg}", file=sys.stderr)
            return 0
        print(f"ERROR: {msg}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError) as e:
        msg = f"network error talking to {args.repository} ({e}); refusing to publish"
        if args.allow_network_failure:
            print(f"WARNING: {msg}", file=sys.stderr)
            return 0
        print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    if local_version in existing:
        print(
            f"ERROR: {package} {local_version} is already published on "
            f"{args.repository}.\n"
            f"  PyPI never lets you replace a published version. Bump\n"
            f"  pyproject.toml's [project].version to a new value\n"
            f"  (e.g. {_suggest_bump(local_version)}) and retry.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {package} {local_version} is not on {args.repository} yet.")
    return 0


def _suggest_bump(v):
    parts = v.split(".")
    try:
        parts[1] = str(int(parts[1]) + 1)
        if len(parts) >= 3:
            parts[2] = "0"
        return ".".join(parts)
    except (IndexError, ValueError):
        return v + ".1"


if __name__ == "__main__":
    sys.exit(main())
