import glob
import json
import sys

REPORTS = sys.argv[1] if len(sys.argv) > 1 else "reports"


def main():
    reports = sorted(glob.glob(f"{REPORTS}/pip-audit-*.json"))
    if not reports:
        print("gate_pip_audit: no pip-audit JSON reports found", file=sys.stderr)
        return 1

    vulnerable = []
    for path in reports:
        with open(path) as f:
            data = json.load(f)
        dependencies = data.get("dependencies", data) if isinstance(data, dict) else data
        for dep in dependencies:
            for vuln in dep.get("vulns", []):
                vulnerable.append((path, dep.get("name"), dep.get("version"), vuln.get("id")))

    for path, name, version, vuln_id in vulnerable:
        print(f"VULN {name}=={version} {vuln_id} ({path})")

    if vulnerable:
        print(f"gate_pip_audit: {len(vulnerable)} known vulnerability/vulnerabilities")
        return 1
    print("gate_pip_audit: no known vulnerabilities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
