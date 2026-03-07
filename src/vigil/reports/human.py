"""Human-readable terminal formatter con colores e iconos."""

import sys

from vigil.core.engine import ScanResult
from vigil.core.finding import Finding, Severity
from vigil import __version__

# Codigos ANSI para colores
_COLORS: dict[str, str] = {
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "gray": "\033[90m",
    "green": "\033[92m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

# Mapeo severidad → (icono unicode, color ANSI)
_SEVERITY_STYLE: dict[Severity, tuple[str, str]] = {
    Severity.CRITICAL: ("\u2717", "red"),      # ✗
    Severity.HIGH: ("\u2717", "red"),           # ✗
    Severity.MEDIUM: ("\u26a0", "yellow"),      # ⚠
    Severity.LOW: ("~", "blue"),
    Severity.INFO: ("i", "cyan"),
}


class HumanFormatter:
    """Formatea resultado del scan para terminal humana."""

    def __init__(
        self,
        *,
        colors: bool = True,
        show_suggestions: bool = True,
        quiet: bool = False,
    ) -> None:
        self._colors = colors
        self._show_suggestions = show_suggestions
        self._quiet = quiet

    def _use_colors(self) -> bool:
        """Determina si usar colores ANSI."""
        if not self._colors:
            return False
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def _colorize(self, text: str, color: str) -> str:
        if not self._use_colors():
            return text
        code = _COLORS.get(color, "")
        reset = _COLORS["reset"]
        return f"{code}{text}{reset}"

    def format(self, result: ScanResult) -> str:
        lines: list[str] = []

        # Header (skip in quiet mode)
        if not self._quiet:
            lines.append("")
            lines.append(
                f"  {self._colorize('vigil', 'bold')} v{__version__} "
                f"\u2014 scanning {result.files_scanned} files..."
            )
            lines.append("")

        # Findings
        if result.findings:
            for finding in result.findings:
                lines.extend(self._format_finding(finding))
        elif not self._quiet and not result.errors:
            lines.append(f"  {self._colorize('No findings.', 'green')}")
            lines.append("")

        # Errors
        if result.errors:
            for error in result.errors:
                lines.append(f"  {self._colorize('ERROR', 'red')}  {error}")
            lines.append("")

        # Summary (skip in quiet mode)
        if not self._quiet:
            lines.append("  " + "\u2500" * 49)
            lines.append(
                f"  {result.files_scanned} files scanned in "
                f"{result.duration_seconds:.1f}s"
            )

            if result.findings:
                counts: list[str] = []
                for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
                            Severity.LOW, Severity.INFO]:
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
                    f"{name} \u2713" for name in result.analyzers_run
                )
                lines.append(f"  {len(result.analyzers_run)} analyzers: {analyzer_list}")

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
            f"  {self._colorize(icon, color)} "
            f"{self._colorize(severity_str, color)}  "
            f"{finding.rule_id}  "
            f"{self._colorize(location, 'gray')}"
        )
        lines.append(f"    {finding.message}")

        if finding.suggestion and self._show_suggestions:
            lines.append(
                f"    {self._colorize('\u2192', 'gray')} "
                f"Suggestion: {finding.suggestion}"
            )

        if finding.location.snippet:
            lines.append(
                f"    {self._colorize('|', 'gray')} "
                f"{finding.location.snippet}"
            )

        lines.append("")
        return lines
