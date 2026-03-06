"""Carga configuracion desde YAML, defaults, y CLI overrides."""

from pathlib import Path

import structlog
import yaml

from vigil.config.schema import ScanConfig

logger = structlog.get_logger()

CONFIG_FILENAMES = [".vigil.yaml", ".vigil.yml", "vigil.yaml", "vigil.yml"]

# Presets de configuracion
STRATEGY_PRESETS: dict[str, dict] = {
    "strict": {
        "fail_on": "medium",
        "deps": {"min_age_days": 60, "min_weekly_downloads": 500},
        "auth": {"max_token_lifetime_hours": 1},
    },
    "standard": {},
    "relaxed": {
        "fail_on": "critical",
        "deps": {"min_age_days": 7, "min_weekly_downloads": 10},
        "auth": {"max_token_lifetime_hours": 72},
    },
}


def find_config_file(start_path: str = ".") -> Path | None:
    """Busca archivo de configuracion subiendo por el arbol de directorios."""
    current = Path(start_path).resolve()

    while True:
        for filename in CONFIG_FILENAMES:
            config_path = current / filename
            if config_path.is_file():
                logger.debug("config_found", path=str(config_path))
                return config_path
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def load_config(
    config_path: str | None = None,
    cli_overrides: dict | None = None,
) -> ScanConfig:
    """Carga configuracion merged: defaults <- YAML <- CLI.

    Args:
        config_path: Ruta explicita al archivo de config. Si None, busca automaticamente.
        cli_overrides: Overrides del CLI (formato plano, se integran a la config).

    Returns:
        ScanConfig validada y merged.
    """
    cli_overrides = cli_overrides or {}
    file_data: dict = {}

    # 1. Cargar desde archivo YAML
    resolved_path: Path | None = None
    if config_path:
        resolved_path = Path(config_path)
        if not resolved_path.is_file():
            logger.warning("config_file_not_found", path=config_path)
            resolved_path = None
    else:
        resolved_path = find_config_file()

    if resolved_path:
        try:
            raw = resolved_path.read_text(encoding="utf-8")
            file_data = yaml.safe_load(raw) or {}
            logger.info("config_loaded", path=str(resolved_path))
        except (yaml.YAMLError, OSError) as e:
            logger.error("config_parse_error", path=str(resolved_path), error=str(e))

    # 2. Merge CLI overrides sobre file_data
    merged = _merge_cli_overrides(file_data, cli_overrides)

    # 3. Validar con Pydantic
    return ScanConfig(**merged)


def _merge_cli_overrides(file_data: dict, cli_overrides: dict) -> dict:
    """Integra overrides del CLI sobre datos del archivo YAML.

    Overrides soportados:
        - fail_on: str
        - output_format: str -> output.format
        - output_file: str -> output.output_file
        - verbose: bool -> output.verbose
        - offline: bool -> deps.offline_mode
        - languages: list[str]
        - categories: list[str]
        - rules_filter: list[str]
        - exclude_rules: list[str]
    """
    data = dict(file_data)

    if "fail_on" in cli_overrides:
        data["fail_on"] = cli_overrides["fail_on"]

    if "languages" in cli_overrides and cli_overrides["languages"]:
        data["languages"] = list(cli_overrides["languages"])

    if "categories" in cli_overrides and cli_overrides["categories"]:
        data["categories"] = list(cli_overrides["categories"])

    if "rules_filter" in cli_overrides and cli_overrides["rules_filter"]:
        data["rules_filter"] = list(cli_overrides["rules_filter"])

    if "exclude_rules" in cli_overrides and cli_overrides["exclude_rules"]:
        data["exclude_rules"] = list(cli_overrides["exclude_rules"])

    # Output overrides
    output_data = data.get("output", {})
    if isinstance(output_data, dict):
        output = dict(output_data)
    else:
        output = {}

    if "output_format" in cli_overrides:
        output["format"] = cli_overrides["output_format"]
    if "output_file" in cli_overrides:
        output["output_file"] = cli_overrides["output_file"]
    if "verbose" in cli_overrides:
        output["verbose"] = cli_overrides["verbose"]
    if "quiet" in cli_overrides and cli_overrides["quiet"]:
        output["show_suggestions"] = False

    if output:
        data["output"] = output

    # Deps overrides
    if "offline" in cli_overrides and cli_overrides["offline"]:
        deps_data = data.get("deps", {})
        if isinstance(deps_data, dict):
            deps = dict(deps_data)
        else:
            deps = {}
        deps["offline_mode"] = True
        data["deps"] = deps

    return data


def _yaml_list(items: list[str]) -> str:
    """Formatea una lista Python como YAML flow sequence."""
    quoted = ", ".join(f'"{item}"' for item in items)
    return f"[{quoted}]"


def generate_config_yaml(strategy: str = "standard") -> str:
    """Genera contenido YAML para .vigil.yaml con el preset seleccionado."""
    preset = STRATEGY_PRESETS.get(strategy, {})
    config = ScanConfig(**preset)

    lines = [
        "# .vigil.yaml - vigil configuration",
        f"# Strategy: {strategy}",
        "#",
        "# Documentation: https://github.com/org/vigil",
        "",
        "# Paths to scan",
        f"include: {_yaml_list(config.include)}",
        f"exclude: {_yaml_list(config.exclude)}",
        f"test_dirs: {_yaml_list(config.test_dirs)}",
        "",
        "# Minimum severity to fail (exit code 1)",
        f'fail_on: "{config.fail_on}"',
        "",
        "# Languages to scan",
        f"languages: {_yaml_list(config.languages)}",
        "",
        "# Dependency analysis",
        "deps:",
        f"  verify_registry: {str(config.deps.verify_registry).lower()}",
        f"  min_age_days: {config.deps.min_age_days}",
        f"  min_weekly_downloads: {config.deps.min_weekly_downloads}",
        f"  similarity_threshold: {config.deps.similarity_threshold}",
        f"  cache_ttl_hours: {config.deps.cache_ttl_hours}",
        "",
        "# Auth pattern analysis",
        "auth:",
        f"  max_token_lifetime_hours: {config.auth.max_token_lifetime_hours}",
        f"  require_auth_on_mutating: {str(config.auth.require_auth_on_mutating).lower()}",
        f"  cors_allow_localhost: {str(config.auth.cors_allow_localhost).lower()}",
        "",
        "# Secret detection",
        "secrets:",
        f"  min_entropy: {config.secrets.min_entropy}",
        f"  check_env_example: {str(config.secrets.check_env_example).lower()}",
        "",
        "# Test quality analysis",
        "tests:",
        f"  min_assertions_per_test: {config.tests.min_assertions_per_test}",
        f"  detect_trivial_asserts: {str(config.tests.detect_trivial_asserts).lower()}",
        f"  detect_mock_mirrors: {str(config.tests.detect_mock_mirrors).lower()}",
        "",
        "# Rule overrides (uncomment to customize)",
        "# rules:",
        '#   DEP-004:',
        '#     severity: "low"',
        "#   AUTH-003:",
        "#     enabled: false",
        "",
    ]
    return "\n".join(lines)
