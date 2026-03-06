# Changelog

All notable changes to vigil will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-03-06

### Added

- **Dependency Analyzer (FASE 1)** — full implementation of CAT-01 rules
  - **DEP-001** (CRITICAL): Detects hallucinated packages that don't exist in PyPI/npm
  - **DEP-002** (HIGH): Flags packages created less than 30 days ago (configurable)
  - **DEP-003** (HIGH): Detects typosquatting via Levenshtein similarity against popular packages corpus
  - **DEP-005** (MEDIUM): Flags packages with no linked source repository
  - **DEP-007** (CRITICAL): Detects pinned versions that don't exist in the registry
- **Dependency file parsers** (`src/vigil/analyzers/deps/parsers.py`)
  - `requirements.txt` / `requirements-dev.txt` with extras, version specs, comments
  - `pyproject.toml` — `[project.dependencies]` and `[project.optional-dependencies]` via `tomllib` (stdlib)
  - `package.json` — `dependencies` and `devDependencies`
  - `find_and_parse_all()` with directory pruning for performance
- **Registry client** (`src/vigil/analyzers/deps/registry_client.py`)
  - PyPI and npm HTTP verification with file-based cache at `~/.cache/vigil/registry/`
  - Configurable cache TTL (default 24h)
  - Network errors assume package exists (no false positives on flaky connections)
  - Version existence checking for pinned dependencies
- **Similarity checker** (`src/vigil/analyzers/deps/similarity.py`)
  - Levenshtein distance with O(min(m,n)) space complexity
  - PyPI name normalization per PEP 503 (hyphens, underscores, dots equivalent)
  - Builtin corpus of ~100 PyPI + ~70 npm popular packages as fallback
  - Configurable similarity threshold (default 0.85)
- **Analyzer registration** — `DependencyAnalyzer` now wired into `scan`, `deps`, and `tests` CLI commands
- **282 tests for FASE 1** (632 total) covering parsers, registry client, similarity, analyzer, integration, and QA edge cases
- **Test fixtures** in `tests/fixtures/deps/` with valid projects, hallucinated deps, npm projects, clean projects, vulnerable projects, and edge cases (empty, comments-only, markers, URLs, malformed)
- **CLI** with 5 subcommands: `scan`, `deps`, `tests`, `init`, `rules`
  - `vigil scan` — full project scan with format/output/fail-on/category/rule filtering
  - `vigil deps` — dependency-focused scan with `--verify/--no-verify`
  - `vigil tests` — test quality analysis with `--min-assertions`
  - `vigil init` — config file generation with `--strategy` presets (strict/standard/relaxed)
  - `vigil rules` — lists all 26 rules with descriptions, severities, and OWASP/CWE references
- **Core engine** (`ScanEngine`) — orchestrates file collection, analyzer execution, rule overrides, and severity sorting
- **Finding model** — `Finding`, `Severity`, `Category`, `Location` dataclasses as the backbone for all scan results
- **ScanResult** — aggregates findings with severity counts, threshold filtering, error tracking, and duration
- **Configuration system**
  - Pydantic v2 models: `ScanConfig`, `DepsConfig`, `AuthConfig`, `SecretsConfig`, `TestQualityConfig`, `OutputConfig`, `RuleOverride`
  - YAML config loader with automatic discovery (`.vigil.yaml` traversing up the directory tree)
  - Three-layer merge: defaults <- YAML file <- CLI flags
  - Strategy presets: `strict`, `standard`, `relaxed`
- **Rule catalog** — 26 rules across 4 categories:
  - `DEP-001..007` — Dependency Hallucination (slopsquatting, typosquatting, freshness)
  - `AUTH-001..007` — Auth & Permission Patterns (missing auth, CORS, JWT, cookies)
  - `SEC-001..006` — Secrets & Credentials (placeholders, low entropy, connection strings)
  - `TEST-001..006` — Test Quality (empty asserts, trivial checks, mock mirrors)
- **Rule registry** — `RuleRegistry` with lookup by ID, category, severity, and override-aware filtering
- **File collector** — discovers files by language extension, respects exclude patterns, always includes dependency manifests
- **BaseAnalyzer protocol** — interface for all analyzers: `name`, `category`, `analyze(files, config)`
- **Output formatters**
  - Human — terminal output with ANSI colors and severity icons
  - JSON — structured output for programmatic consumption
  - JUnit XML — for CI dashboard integration
  - SARIF 2.1.0 — for GitHub/GitLab Code Scanning integration
- **Summary builder** — statistical breakdown by severity, category, and rule
- **Structured logging** — structlog configured to stderr, verbose/quiet modes
- **Example config** — `.vigil.example.yaml` with documented options
- **Exit codes** — 0 (clean), 1 (findings above threshold), 2 (execution error)
- **`--changed-only`** — git-aware mode for pre-commit hooks (scans only changed files)
- **`--offline`** — skip all HTTP requests to registries
- **`python -m vigil`** support
- **350 tests** covering core models, engine, config, CLI, all formatters, and edge cases (FASE 0)

### Fixed

- **`--rule` flag not filtering findings** — `rules_filter` in ScanConfig was set by CLI but `_apply_rule_overrides` never checked it; findings were returned unfiltered. Now only findings matching specified rule IDs are included.
- **Duplicate chalk entry in npm corpus** — `similarity.py` had two entries for `"chalk"` (22M and 300K downloads); the lower value overwrote the correct one. Removed the duplicate.
- **Environment markers breaking requirements.txt parsing** — dependencies with markers like `pywin32; sys_platform == "win32"` were silently skipped. Parser now strips markers before matching.
- **`_extract_roots` returning CWD for empty input** — when no files matched, the analyzer would scan the current working directory instead of returning no findings. Now returns `[]` and exits early.
- **CLI tests scanning project root** — refactored `test_cli.py` and `test_cli_edge_cases.py` to use `tmp_path` with clean files, preventing test fixture interference.
- **File collector exclude pattern over-matching** — exclude `build/` no longer excludes `rebuild/` (changed from substring to path-component matching)
- **Config YAML generation** — `generate_config_yaml()` now produces valid YAML flow sequences instead of Python list repr syntax
- **SARIF rule name PascalCase** — rule names now properly capitalize each word (e.g., `PackageNotInRegistry` instead of `Package not in registry`)
- **`--output` with nested directories** — parent directories are created automatically when they don't exist
- **`fail_on` validation** — `ScanConfig.fail_on` now uses `Literal` type and rejects invalid values at parse time
- **`TestQualityConfig` pytest collection warning** — renamed from `TestsConfig` and added `__test__ = False` to prevent pytest from trying to collect it as a test class
- **File collector performance** — replaced `Path.rglob("*")` with `os.walk()` + directory pruning, fixing >2 minute scan times on WSL when `.venv/` or `node_modules/` are present
