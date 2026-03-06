# CLAUDE.md — vigil

## What is vigil

vigil is a deterministic CLI static analysis tool that detects vulnerabilities and risk patterns **specific to AI-generated code**. It does NOT use LLMs to function. It complements Semgrep, Snyk, CodeQL — it does not replace them.

Key problem: slopsquatting (hallucinated dependencies), insecure auth patterns, hardcoded secrets from placeholders, and empty test theater produced by AI coding agents.

## Quick Reference

```bash
# Setup
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run
vigil scan src/
vigil deps --verify
vigil tests tests/
vigil rules
vigil init --strategy standard

# Test
pytest tests/ -v
pytest tests/ -v --cov=vigil

# Lint
ruff check src/ tests/
```

## Project Structure

```
src/vigil/
  __init__.py              # __version__
  __main__.py              # python -m vigil
  cli.py                   # Click CLI (main, scan, deps, tests, init, rules)
  config/
    schema.py              # Pydantic v2 models (ScanConfig, DepsConfig, etc.)
    loader.py              # YAML loading + CLI override merging + strategy presets
    rules.py               # RuleDefinition dataclass + RULES_V0 catalog (26 rules)
  core/
    finding.py             # Finding, Severity, Category, Location (dataclasses)
    engine.py              # ScanEngine orchestrator + ScanResult
    file_collector.py      # File discovery with language/exclude filtering
    rule_registry.py       # RuleRegistry with category/severity/override filtering
  analyzers/
    base.py                # BaseAnalyzer Protocol
    deps/                  # CAT-01: Dependency Hallucination (FASE 1)
    auth/                  # CAT-02: Auth & Permission Patterns (FASE 2)
    secrets/               # CAT-03: Secrets & Credentials (FASE 2)
    tests/                 # CAT-06: Test Quality (FASE 3)
  reports/
    formatter.py           # BaseFormatter Protocol + get_formatter() factory
    human.py               # Terminal output with ANSI colors
    json_fmt.py            # JSON output
    junit.py               # JUnit XML
    sarif.py               # SARIF 2.1.0 (GitHub/GitLab integration)
    summary.py             # Statistical summary builder
  logging/
    setup.py               # structlog configuration (logs to stderr)
tests/                     # Mirrors src/vigil/ structure
data/                      # Static data (popular packages corpus, placeholder patterns)
```

## Architecture Rules

- **ScanEngine is the orchestrator.** Analyzers register on it; they don't know each other. The engine collects files, runs analyzers, applies rule overrides, sorts findings.
- **Every analyzer implements BaseAnalyzer Protocol:** property `name`, property `category`, method `analyze(files: list[str], config: ScanConfig) -> list[Finding]`.
- **An analyzer error must never crash the scan.** Exceptions are caught per-analyzer, logged in `ScanResult.errors`, and the engine continues.
- **Findings flow:** Analyzer produces `Finding` -> Engine collects -> Engine applies overrides/filters -> Engine sorts by severity -> Formatter renders.

## Code Conventions

- **Python 3.12+**. Use `str | None` not `Optional[str]`. Full type hints on all functions.
- **Dataclasses** for simple data (Finding, Location, RuleDefinition). **Pydantic BaseModel** for config that needs validation (ScanConfig, DepsConfig, etc.).
- **Dependencies** (only these): click, pydantic v2, httpx, structlog, pyyaml. Do not add others without justification.
- **Logging:** `structlog.get_logger()`. Logs go to stderr. Only findings/reports go to stdout. No `print()` — all user output goes through report formatters.
- **Rule IDs** follow format `CAT-NNN` (e.g., DEP-001, AUTH-003, SEC-002, TEST-001).
- **Exit codes:** 0 = no findings above threshold, 1 = findings found, 2 = execution error.
- **CLI in English.** Internal documentation in Spanish.

## Finding Requirements

Every Finding must have:
- `rule_id`: format "CAT-NNN"
- `category`: Category enum value
- `severity`: Severity enum value
- `message`: actionable, specific (not "possible issue detected" but "Package 'x' does not exist in pypi")
- `location`: file + line when possible
- `suggestion`: concrete fix (not "review this" but "Remove 'x' and search pypi for the correct package")

## Rule Categories (V0)

| Category | Prefix | Rules | Description |
|---|---|---|---|
| Dependency Hallucination | DEP-001..007 | 7 | Packages that don't exist, typosquatting, suspiciously new |
| Auth & Permission | AUTH-001..007 | 7 | Missing auth middleware, CORS *, hardcoded JWT secrets |
| Secrets & Credentials | SEC-001..006 | 6 | Placeholder secrets, low-entropy hardcoded values, .env.example copies |
| Test Quality | TEST-001..006 | 6 | Empty asserts, trivial checks, skipped tests, mock mirrors |

## Implementation Phases

- **FASE 0** (DONE): Scaffolding, config, core engine, CLI, formatters, rule catalog — 350 tests
- **FASE 1** (DONE): DependencyAnalyzer (parsers, registry client, similarity/typosquatting, popular packages corpus) — 120 tests, 470 total
- **FASE 2**: AuthAnalyzer + SecretsAnalyzer (regex pattern matching for FastAPI/Flask/Express)
- **FASE 3**: TestQualityAnalyzer (pytest/jest assertion checking, mock mirror detection)
- **FASE 4**: Report formatters polish
- **FASE 5**: Full integration, CLI wiring, test fixtures with realistic AI-generated code
- **FASE 6**: Popular packages data generation, polish

## Plan Documents

- `Vigil-Producto-Vision.md` — Product vision, problem statement, market positioning, rule definitions
- `Vigil-V0-Plan-Implementacion.md` — Full V0 implementation plan with reference code for every module

## Key Design Decisions

- **Deterministic only.** No LLMs, no AI, no API costs. Static rules, heuristics, and registry verification.
- **Registry verification uses cache** at `~/.cache/vigil/registry/` with configurable TTL (default 24h). Never repeat HTTP requests in the same scan.
- **`--offline` mode** skips all HTTP requests. Only static checks run.
- **Detection strategy for V0 is regex-based.** AST parsing is V1 scope.
- **Config merges three layers:** defaults <- YAML file (.vigil.yaml) <- CLI flags.

## Testing

- Tests in `tests/` mirror the `src/vigil/` structure.
- Use `pytest` with `tmp_path` fixture for filesystem tests.
- Test negative cases (legitimate code should NOT generate findings).
- Test edge cases: empty files, non-UTF8 encoding, missing dependency files, repos without git.
- Fixtures in `tests/fixtures/` for realistic sample code.
