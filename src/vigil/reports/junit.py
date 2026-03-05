"""JUnit XML output formatter."""

import xml.etree.ElementTree as ET

from vigil.core.engine import ScanResult
from vigil.core.finding import Finding, Severity


class JunitFormatter:
    """Formatea resultado del scan como JUnit XML."""

    def format(self, result: ScanResult) -> str:
        testsuites = ET.Element("testsuites")
        testsuite = ET.SubElement(
            testsuites,
            "testsuite",
            name="vigil",
            tests=str(len(result.findings) or 1),
            failures=str(len(result.findings)),
            errors=str(len(result.errors)),
            time=f"{result.duration_seconds:.3f}",
        )

        if not result.findings:
            # Agregar un test case exitoso cuando no hay findings
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

        failure_type = "error" if finding.severity in (Severity.CRITICAL, Severity.HIGH) else "warning"
        failure = ET.SubElement(
            testcase,
            "failure",
            message=finding.message,
            type=failure_type,
        )
        text_parts = [f"Rule: {finding.rule_id}"]
        text_parts.append(f"Severity: {finding.severity.value}")
        text_parts.append(f"File: {location}")
        if finding.suggestion:
            text_parts.append(f"Suggestion: {finding.suggestion}")
        failure.text = "\n".join(text_parts)
