"""JUnit XML output formatter."""

import xml.etree.ElementTree as ET

from vigil import __version__
from vigil.core.engine import ScanResult
from vigil.core.finding import Finding, Severity


class JunitFormatter:
    """Formatea resultado del scan como JUnit XML.

    Mapea findings de vigil al modelo JUnit XML:
    - Cada finding es un <testcase> con un <failure>.
    - Si no hay findings, se agrega un testcase exitoso.
    - Los errores de analyzers se mapean a <testcase> con <error>.
    """

    def format(self, result: ScanResult) -> str:
        testsuites = ET.Element("testsuites")
        testsuite = ET.SubElement(
            testsuites,
            "testsuite",
            name="vigil",
            tests=str((len(result.findings) + len(result.errors)) or 1),
            failures=str(len(result.findings)),
            errors=str(len(result.errors)),
            time=f"{result.duration_seconds:.3f}",
        )

        # Property list con metadata del scan
        properties = ET.SubElement(testsuite, "properties")
        ET.SubElement(properties, "property", name="vigil.version", value=__version__)
        ET.SubElement(
            properties, "property",
            name="vigil.files_scanned", value=str(result.files_scanned),
        )
        if result.analyzers_run:
            ET.SubElement(
                properties, "property",
                name="vigil.analyzers", value=",".join(result.analyzers_run),
            )

        if not result.findings:
            ET.SubElement(
                testsuite,
                "testcase",
                name="vigil-scan",
                classname="vigil",
                time=f"{result.duration_seconds:.3f}",
            )
        else:
            for finding in result.findings:
                self._add_testcase(testsuite, finding)

        for error in result.errors:
            error_case = ET.SubElement(
                testsuite,
                "testcase",
                name="vigil-error",
                classname="vigil",
            )
            ET.SubElement(error_case, "error", message=error)

        ET.indent(testsuites, space="  ")
        return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)

    def _add_testcase(self, testsuite: ET.Element, finding: Finding) -> None:
        location = finding.location.file
        if finding.location.line is not None:
            location += f":{finding.location.line}"

        testcase = ET.SubElement(
            testsuite,
            "testcase",
            name=f"{finding.rule_id}: {location}",
            classname=f"vigil.{finding.category.value}",
        )

        failure_type = (
            "error"
            if finding.severity in (Severity.CRITICAL, Severity.HIGH)
            else "warning"
        )
        failure = ET.SubElement(
            testcase,
            "failure",
            message=finding.message,
            type=failure_type,
        )
        text_parts = [f"Rule: {finding.rule_id}"]
        text_parts.append(f"Severity: {finding.severity.value}")
        text_parts.append(f"Category: {finding.category.value}")
        text_parts.append(f"File: {location}")
        if finding.suggestion:
            text_parts.append(f"Suggestion: {finding.suggestion}")
        if finding.location.snippet:
            text_parts.append(f"Snippet: {finding.location.snippet}")
        failure.text = "\n".join(text_parts)
