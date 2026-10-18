# Build gate policy

This is the policy for the Implementation & build and Testing gates in [docs/plan.md](plan.md) section 9. It is enforced by the [Jenkinsfile](../Jenkinsfile). Every rule below makes the pipeline **fail** (red), not merely unstable (yellow): each stage is wrapped so a violation sets the build result to FAILURE. The pipeline still runs the remaining stages and archives every report, so one red build shows all findings at once.

A build is green only when all six gates pass. All reports are archived as artifacts on every build (`reports/**`), and the test results are published as JUnit.

## Rules

### 1. Secret scan — fail on any finding

- **Tool:** gitleaks (`detect` over the git history).
- **Rule:** any leak fails the build.
- **Why:** A signing key, password or token in the history is asset A2/A3 exposure (threat T11). Once committed it must be treated as compromised, so there is no "low severity" secret; one finding is enough to stop the build. gitleaks runs before the build stage, so it scans only committed content and never the generated `secrets/` directory.

### 2. Build — fail if the carreport wheel or an unlisted dependency is rejected

- **Tool:** `pip install --require-hashes --only-binary=:all:` in each image, and `--no-index --no-deps` for the carreport wheel.
- **Rule:** any dependency without a matching hash, any package not in the lock file, or a carreport wheel whose contents do not match, makes `docker compose build` fail, which fails the build.
- **Why:** This is the "only listed dependencies are installed" gate (threats T6, supply chain). `--require-hashes` refuses a package that is missing a hash or whose download does not match, so an added or tampered dependency cannot enter the image. `--no-index` keeps the carreport install from reaching PyPI, preventing dependency confusion.

### 3. SAST — fail on HIGH severity, or HIGH confidence with MEDIUM severity

- **Tool:** bandit over each service's `app/`, evaluated by [scripts/ci/gate_bandit.py](../scripts/ci/gate_bandit.py).
- **Rule:** a finding blocks the build when `severity == HIGH`, or when `severity == MEDIUM and confidence == HIGH`. Lower findings are reported but do not block.
- **Why:** High-severity findings are likely exploitable and must stop the build. Raising medium-severity findings to blocking only when bandit is highly confident keeps the gate strict without drowning it in low-confidence noise.
- **Limitation (important):** bandit does **not** catch the planted SQL injection V3. The injection is built by `+=` with an f-string fragment (`" AND make = '{make}'"`) that contains no SQL keyword, so bandit's B608 heuristic does not recognise it as query construction. A control test confirmed bandit flags B608 only when the `SELECT` itself is in the f-string. **The gate for SQL injection is therefore the authorization test** `test_sql_injection_in_make_filter_returns_no_foreign_cars` (threat T16), enforced by rule 5, not SAST. SAST is defence in depth, not the SQLi gate.

### 4. Dependency scan — fail on any known vulnerability

- **Tool:** pip-audit over every `requirements.txt` and `requirements-dev.txt`, evaluated by [scripts/ci/gate_pip_audit.py](../scripts/ci/gate_pip_audit.py).
- **Rule:** any dependency with a known advisory fails the build.
- **Why:** A pinned dependency with a public advisory is a known, fixable risk. The lock files pin exact versions, so a vulnerable version stays in place until someone updates it; failing the build forces that update rather than letting the known hole ship.

### 5. Tests — fail on any failed test

- **Tool:** pytest in each service's test image, JUnit XML published.
- **Rule:** any failing test in any service fails the build.
- **Why:** The suites encode the functional requirements (FR1–FR6) and the authorization and token rules (T1–T16 where they are unit-testable). A single failure means a requirement or a control is broken. This gate is what catches the planted vulnerabilities V1 (T8), V2 (T15), V3 (T16) and V4 (T9): while they are present, the matching tests fail and the build is red. It is in particular the gate for the SQL injection that SAST misses (see rule 3).

### 6. Integration — fail if report-service can reach the gateway

- **Tool:** a fresh `docker compose` environment, seeded, with a socket check from inside report-service.
- **Rule:** the build fails unless report-service can reach car-service **and** cannot reach auth-gateway.
- **Why:** This is the network segmentation for threat T14 and the least-privilege design: report-service must talk to car-service to do its job but must have no path back to the gateway. A unit test cannot check Docker networking, so this runs against the real compose network. If a future change puts report-service on the gateway network, this gate catches it.

## Current state with V1–V4 planted

While the four planted vulnerabilities are present, the pipeline is red, driven by **rule 5 (Tests)**: the authorization tests for V1–V4 fail. Secret scan, build, SAST, dependency scan and integration all pass, which is expected — the planted flaws are application-logic and authorization bugs, and only V3 is even in SAST's remit (where bandit misses it by design). After each vulnerability is fixed in its own commit, its tests pass again and the gate clears.
