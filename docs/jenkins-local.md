# Running Jenkins locally and connecting it to GitHub

The pipeline is defined in the repository's [Jenkinsfile](../Jenkinsfile). It runs on every push and pull request and has these stages: Checkout, Secret scan (gitleaks), Build, SAST (bandit), Dependency scan (pip-audit), Tests, Integration (network isolation check). All reports are archived as build artifacts, also when a stage is unstable. There are no gate rules yet; failing scans mark the stage UNSTABLE but do not fail the build (that is SKOLE-28).

## 1. Start Jenkins in Docker

The pipeline itself runs `docker` commands, so Jenkins needs access to a Docker daemon. The simplest local setup mounts the host Docker socket into the Jenkins container.

```bash
docker network create jenkins || true
```

```bash
docker run -d --name jenkins \
  -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --group-add "$(stat -f '%g' /var/run/docker.sock)" \
  jenkins/jenkins:lts-jdk17
```

The Jenkins image has no Docker client. Install it once inside the container:

```bash
docker exec -u root jenkins bash -c "apt-get update && apt-get install -y docker.io docker-compose-plugin"
```

Get the first-run admin password and open Jenkins:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Open http://localhost:8080, paste the password, install the suggested plugins, and create the admin user. Make sure the **Pipeline**, **Git**, and **JUnit** plugins are installed (the suggested set includes them).

## 2. Connect your private GitHub repository

Pushing to a private repository needs a credential. Use a fine-grained personal access token with read access to the repository's contents.

1. On GitHub: Settings → Developer settings → Personal access tokens → create a token with **Contents: Read-only** for this repository. Copy it.
2. In Jenkins: Manage Jenkins → Credentials → System → Global → Add Credentials.
   - Kind: **Username with password**
   - Username: your GitHub username
   - Password: the token
   - ID: `github-token`

### Create the pipeline job

1. New Item → name it `car-valuation` → **Multibranch Pipeline** → OK.
2. Branch Sources → Add source → **GitHub**.
   - Credentials: `github-token`
   - Repository HTTPS URL: `https://github.com/<you>/<repo>.git`
3. Build Configuration → by **Jenkinsfile** (the default path `Jenkinsfile`).
4. Save. Jenkins scans the branches and PRs and runs the pipeline on each.

A multibranch pipeline builds every branch and every pull request automatically, which matches "runs on each push and PR".

### Triggering builds automatically

For local Jenkins without a public URL, either:

- **Poll** (simplest): in the job, Scan Repository Triggers → "Periodically if not otherwise run" → 1 minute. Jenkins checks GitHub for new commits.
- **Webhook** (instant): expose Jenkins with a tunnel (for example `cloudflared` or `ngrok`) and add a webhook in the GitHub repository settings pointing at `https://<tunnel>/github-webhook/`.

## 3. Run the pipeline once by hand

In the job view, pick a branch and click **Build Now**. Watch the stages in **Stage View**. When it finishes:

- **Artifacts**: the build page lists everything under `reports/` — `gitleaks.json`, `bandit-*.json`, `bandit-*.txt`, `pip-audit-*.json`, `junit-*.xml`, `integration-network.txt`.
- **Test Result**: the JUnit XML is parsed and shown as a test trend.

While the four planted vulnerabilities (V1–V4) are present, the Tests stage is UNSTABLE and the failing tests appear in the Test Result. The build still completes and archives all reports, because gate rules come in SKOLE-28.

## Notes

- The agent needs Docker and `docker compose`. The socket mount above gives the Jenkins container the host daemon.
- The Build stage runs `scripts/generate_secrets.sh`, so each build gets a fresh key pair and seed passwords inside the workspace. They are never committed (`secrets/` is git-ignored).
- The Secret scan runs before the Build stage, so it scans only committed content; the generated `secrets/` directory does not exist yet at that point.
- `reports/` is git-ignored so local runs do not leave artifacts in the working tree.
