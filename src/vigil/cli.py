"""Click CLI completa de vigil."""

import sys
from pathlib import Path

import click

from vigil import __version__
from vigil.config.loader import generate_config_yaml, load_config
from vigil.config.rules import RULES_V0
from vigil.core.engine import ScanEngine
from vigil.core.finding import Severity
from vigil.logging.setup import setup_logging
from vigil.reports.formatter import get_formatter


class ExitCode:
    SUCCESS = 0
    FINDINGS = 1
    ERROR = 2


@click.group()
@click.version_option(version=__version__, prog_name="vigil")
def main() -> None:
    """vigil -- Security scanner for AI-generated code."""


@main.command()
@click.argument("paths", nargs=-1, default=(".",))
@click.option("--config", "-c", type=click.Path(), help="Config file (.vigil.yaml)")
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["human", "json", "junit", "sarif"]),
    default="human",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), help="Output file")
@click.option(
    "--fail-on",
    type=click.Choice(["critical", "high", "medium", "low"]),
    default="high",
    help="Minimum severity to fail (exit code 1)",
)
@click.option(
    "--category", "-C", multiple=True,
    type=click.Choice(["dependency", "auth", "secrets", "test-quality"]),
    help="Only run specific categories",
)
@click.option("--rule", "-r", multiple=True, help="Only run specific rules (e.g. DEP-001)")
@click.option("--exclude-rule", "-R", multiple=True, help="Exclude specific rules")
@click.option(
    "--language", "-l", multiple=True,
    type=click.Choice(["python", "javascript"]),
    help="Only scan specific languages",
)
@click.option("--offline", is_flag=True, help="Don't make HTTP requests to registries")
@click.option(
    "--changed-only", is_flag=True,
    help="Only scan files changed since last commit (for pre-commit)",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--quiet", "-q", is_flag=True, help="Only output findings, no summary")
def scan(
    paths: tuple[str, ...],
    config: str | None,
    output_format: str,
    output: str | None,
    fail_on: str,
    category: tuple[str, ...],
    rule: tuple[str, ...],
    exclude_rule: tuple[str, ...],
    language: tuple[str, ...],
    offline: bool,
    changed_only: bool,
    verbose: bool,
    quiet: bool,
) -> None:
    """Scan code for AI-generated security issues.

    Examples:

      vigil scan src/

      vigil scan . --format sarif --output report.sarif

      vigil scan src/ --category dependency --fail-on critical

      vigil scan . --changed-only

      vigil scan src/ --offline
    """
    setup_logging(verbose=verbose)

    try:
        scan_config = load_config(
            config_path=config,
            cli_overrides={
                "fail_on": fail_on,
                "output_format": output_format,
                "output_file": output,
                "verbose": verbose,
                "quiet": quiet,
                "offline": offline,
                "languages": list(language) if language else None,
                "categories": list(category) if category else None,
                "rules_filter": list(rule) if rule else None,
                "exclude_rules": list(exclude_rule) if exclude_rule else None,
            },
        )
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(ExitCode.ERROR)

    # Resolver paths
    scan_paths = list(paths)
    if changed_only:
        scan_paths = _get_changed_files()
        if not scan_paths:
            click.echo("No changed files to scan.", err=True)
            sys.exit(ExitCode.SUCCESS)

    # Ejecutar scan
    engine = ScanEngine(scan_config)
    _register_analyzers(engine)
    result = engine.run(scan_paths)

    # Formatear y escribir output
    formatter = get_formatter(
        output_format,
        colors=scan_config.output.colors,
        show_suggestions=scan_config.output.show_suggestions,
        quiet=quiet,
    )
    report = formatter.format(result)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        if output_format == "human":
            click.echo(report)
    else:
        click.echo(report)

    # Determinar exit code
    threshold = Severity(fail_on)
    if result.findings_above(threshold):
        sys.exit(ExitCode.FINDINGS)
    if result.errors:
        sys.exit(ExitCode.ERROR)
    sys.exit(ExitCode.SUCCESS)


@main.command()
@click.argument("path", default=".")
@click.option(
    "--verify/--no-verify", default=True,
    help="Verify packages exist in registry",
)
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["human", "json"]),
    default="human",
)
@click.option("--offline", is_flag=True)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def deps(
    path: str,
    verify: bool,
    output_format: str,
    offline: bool,
    verbose: bool,
) -> None:
    """Check dependencies for hallucinated or suspicious packages.

    Examples:

      vigil deps

      vigil deps --no-verify

      vigil deps /path/to/project
    """
    setup_logging(verbose=verbose)

    scan_config = load_config(
        cli_overrides={
            "output_format": output_format,
            "offline": offline or not verify,
            "verbose": verbose,
            "categories": ["dependency"],
        },
    )

    engine = ScanEngine(scan_config)
    _register_analyzers(engine)
    result = engine.run([path])

    formatter = get_formatter(output_format)
    click.echo(formatter.format(result))

    threshold = Severity(scan_config.fail_on)
    if result.findings_above(threshold):
        sys.exit(ExitCode.FINDINGS)
    sys.exit(ExitCode.SUCCESS)


@main.command("tests")
@click.argument("test_paths", nargs=-1, default=("tests/",))
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["human", "json"]),
    default="human",
)
@click.option("--min-assertions", type=int, default=1)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def check_tests(
    test_paths: tuple[str, ...],
    output_format: str,
    min_assertions: int,
    verbose: bool,
) -> None:
    """Analyze test quality for empty assertions and test theater.

    Examples:

      vigil tests

      vigil tests tests/ --min-assertions 2

      vigil tests --format json
    """
    setup_logging(verbose=verbose)

    scan_config = load_config(
        cli_overrides={
            "output_format": output_format,
            "verbose": verbose,
            "categories": ["test-quality"],
        },
    )
    scan_config.tests.min_assertions_per_test = min_assertions

    engine = ScanEngine(scan_config)
    _register_analyzers(engine)
    result = engine.run(list(test_paths))

    formatter = get_formatter(output_format)
    click.echo(formatter.format(result))

    threshold = Severity(scan_config.fail_on)
    if result.findings_above(threshold):
        sys.exit(ExitCode.FINDINGS)
    sys.exit(ExitCode.SUCCESS)


@main.command()
@click.argument("path", default=".")
@click.option(
    "--strategy",
    type=click.Choice(["strict", "standard", "relaxed"]),
    default="standard",
    help="Preset configuration",
)
@click.option("--force", is_flag=True, help="Overwrite existing config")
def init(path: str, strategy: str, force: bool) -> None:
    """Initialize vigil configuration.

    Generates a .vigil.yaml with sensible defaults.

    Examples:

      vigil init

      vigil init --strategy strict

      vigil init --strategy relaxed
    """
    target_dir = Path(path).resolve()
    if not target_dir.is_dir():
        click.echo(f"Directory does not exist: {target_dir}", err=True)
        sys.exit(ExitCode.ERROR)

    target = target_dir / ".vigil.yaml"
    if target.exists() and not force:
        click.echo(f"Config file already exists: {target}", err=True)
        click.echo("Use --force to overwrite.", err=True)
        sys.exit(ExitCode.ERROR)

    content = generate_config_yaml(strategy)
    target.write_text(content, encoding="utf-8")
    click.echo(f"Created {target} with '{strategy}' strategy.")


@main.command()
def rules() -> None:
    """List all available rules with descriptions.

    Examples:

      vigil rules
    """
    current_category = None
    for rule in RULES_V0:
        if rule.category != current_category:
            current_category = rule.category
            click.echo(f"\n  {current_category.value.upper()}")
            click.echo("  " + "-" * 40)

        severity_str = rule.default_severity.value.upper().ljust(8)
        click.echo(f"  {rule.id:<10} {severity_str}  {rule.name}")
        click.echo(f"  {'':10} {'':8}  {rule.description}")
        refs = []
        if rule.owasp_ref:
            refs.append(f"OWASP: {rule.owasp_ref}")
        if rule.cwe_ref:
            refs.append(rule.cwe_ref)
        if refs:
            click.echo(f"  {'':10} {'':8}  [{', '.join(refs)}]")


def _register_analyzers(engine: ScanEngine) -> None:
    """Registra todos los analyzers disponibles en el engine."""
    from vigil.analyzers.deps import DependencyAnalyzer
    from vigil.analyzers.auth import AuthAnalyzer
    from vigil.analyzers.secrets import SecretsAnalyzer
    from vigil.analyzers.tests import TestQualityAnalyzer

    engine.register_analyzer(DependencyAnalyzer())
    engine.register_analyzer(AuthAnalyzer())
    engine.register_analyzer(SecretsAnalyzer())
    engine.register_analyzer(TestQualityAnalyzer())


def _get_changed_files() -> list[str]:
    """Obtiene archivos cambiados desde el ultimo commit via git.

    Incluye archivos con cambios staged, unstaged, y untracked.
    Usa git status --porcelain -z para manejar filenames con espacios.
    """
    import subprocess

    try:
        # Usar -z para separar con NUL byte (maneja filenames con espacios)
        result = subprocess.run(
            ["git", "status", "--porcelain", "-u", "-z"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        files: list[str] = []
        # Output separado por NUL bytes, formato: "XY filename\0" o "XY old\0new\0"
        entries = result.stdout.split("\0")
        i = 0
        while i < len(entries):
            entry = entries[i]
            if not entry:
                i += 1
                continue

            status = entry[:2]
            filename = entry[3:]

            # Renames (R) y copies (C) tienen un segundo campo con el nuevo nombre
            if status[0] in ("R", "C"):
                i += 1
                if i < len(entries):
                    filename = entries[i]  # Usar el nuevo nombre

            # Ignorar archivos eliminados
            if status.strip() != "D" and status[1] != "D":
                files.append(filename)

            i += 1

        return files
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
