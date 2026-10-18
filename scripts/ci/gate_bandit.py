import glob
import json
import sys

REPORTS = sys.argv[1] if len(sys.argv) > 1 else "reports"


def blocks(issue):
    severity = issue.get("issue_severity", "").upper()
    confidence = issue.get("issue_confidence", "").upper()
    if severity == "HIGH":
        return True
    if severity == "MEDIUM" and confidence == "HIGH":
        return True
    return False


def main():
    reports = sorted(glob.glob(f"{REPORTS}/bandit-*.json"))
    if not reports:
        print("gate_bandit: no bandit JSON reports found", file=sys.stderr)
        return 1

    violations = []
    for path in reports:
        with open(path) as f:
            data = json.load(f)
        for issue in data.get("results", []):
            if blocks(issue):
                violations.append((path, issue))

    for path, issue in violations:
        print(
            f"BLOCK {issue.get('test_id')} severity={issue.get('issue_severity')} "
            f"confidence={issue.get('issue_confidence')} "
            f"{issue.get('filename')}:{issue.get('line_number')} ({path})"
        )

    if violations:
        print(f"gate_bandit: {len(violations)} blocking finding(s) (HIGH severity, or MEDIUM severity + HIGH confidence)")
        return 1
    print("gate_bandit: no blocking findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
