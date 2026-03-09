# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in vigil, please report it responsibly. **Do not open a public GitHub issue.**

### How to report

Send an email to **security@vigil.dev** with:

- A description of the vulnerability.
- Steps to reproduce the issue.
- The potential impact.
- Any suggested fix, if you have one.

### What to expect

- **Acknowledgment** within 48 hours.
- **Initial assessment** within 7 days.
- **Fix or mitigation** within 30 days for confirmed vulnerabilities.
- **Credit** in the release notes (unless you prefer to remain anonymous).

## Scope

### In scope

- Vulnerabilities in vigil's own code (`src/vigil/`).
- Configuration parsing that could lead to code execution or file system access.
- HTTP request handling (registry verification) that could leak sensitive data.
- Cache poisoning in `~/.cache/vigil/registry/`.
- Dependency confusion or supply chain issues in vigil's own dependencies.

### Out of scope

- Vulnerabilities in the projects that vigil scans (that's what vigil detects, not what it fixes).
- False positives or false negatives in detection rules (report these as regular issues).
- Denial of service via large input files (vigil is a local tool, not a service).

## Security Design

### Network requests

vigil makes HTTP GET requests to public registries (PyPI, npm) to verify package existence. These requests:

- Only send package names (no project source code or metadata).
- Can be disabled entirely with `--offline`.
- Are cached locally at `~/.cache/vigil/registry/`.

### No telemetry

vigil does not send telemetry, analytics, or usage data to any server.

### No code execution

vigil performs static analysis only. It never executes, imports, or evaluates the code it scans.

### Local-only operation

All analysis runs locally. No data leaves the machine except for registry verification requests (which can be disabled).
