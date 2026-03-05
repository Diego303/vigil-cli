"""Human-readable terminal formatter con colores e iconos."""

import sys

from vigil.core.engine import ScanResult
from vigil.core.finding import Finding, Severity
from vigil import __version__

# Codigos ANSI para colores
_COLORS = {
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "gray": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

_SEVERITY_STYLE: dict[Severity, tuple[str, str]] = {
    Severity.CRITICAL: ("X", "red"),
    Severity.HIGH: ("X", "red"),
    Severity.MEDIUM: ("!", "yellow"),
    Severity.LOW: ("~", "blue"),
    Severity.INFO: ("i", "cyan"),
}


def _use_colors() -> bool:
    """Determina si la terminal soporta colores."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _colorize(text: str, color: str) -> str:
    if not _use_colors():
        return text
    code = _COLORS.get(color, "")
    reset = _COLORS["reset"]
    return f"{code}{text}{reset}"


class HumanFormatter:
    """Formatea resultado del scan para terminal humana."""

    def format(self, result: ScanResult) -> str:
        lines: list[str] = []

        # Header
        lines.append("")
        lines.append(
            f"  {_colorize('vigil', 'bold')} v{__version__} "
            f"— scanned {result.files_scanned} files"
        )
        lines.append("")

        # Findings
        if result.findings:
            for finding in result.findings:
                lines.extend(self._format_finding(finding))
        else:
            lines.append(f"  {_colorize('No findings.', 'gray')}")
            lines.append("")

        # Errors
        if result.errors:
            for error in result.errors:
                lines.append(f"  {_colorize('ERROR', 'red')}  {error}")
            lines.append("")

        # Summary
        lines.append("  " + "-" * 49)
        lines.append(
            f"  {result.files_scanned} files scanned in "
            f"{result.duration_seconds:.1f}s"
        )

        if result.findings:
            counts = []
            for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
                count = sum(1 for f in result.findings if f.severity == sev)
                if count > 0:
                    counts.append(f"{count} {sev.value}")
            lines.append(
                f"  {len(result.findings)} findings: {', '.join(counts)}"
            )
        else:
            lines.append("  0 findings")

        if result.analyzers_run:
            analyzer_list = ", ".join(
                f"{name}" for name in result.analyzers_run
            )
            lines.append(f"  analyzers: {analyzer_list}")

        lines.append("")
        return "\n".join(lines)

    def _format_finding(self, finding: Finding) -> list[str]:
        lines: list[str] = []
        icon, color = _SEVERITY_STYLE[finding.severity]

        severity_str = finding.severity.value.upper().ljust(8)
        location = finding.location.file
        if finding.location.line is not None:
            location += f":{finding.location.line}"

        lines.append(
            f"  {_colorize(icon, color)} "
            f"{_colorize(severity_str, color)}  "
            f"{finding.rule_id}  "
            f"{_colorize(location, 'gray')}"
        )
        lines.append(f"    {finding.message}")

        if finding.suggestion:
            lines.append(
                f"    {_colorize('->', 'gray')} Suggestion: {finding.suggestion}"
            )

        if finding.location.snippet:
            lines.append(f"    {_colorize('|', 'gray')} {finding.location.snippet}")

        lines.append("")
        return lines
