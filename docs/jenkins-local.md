# Running Jenkins locally and connecting it to GitHub

The pipeline is defined in the repository's [Jenkinsfile](../Jenkinsfile). It runs on every push and pull request and has these stages: Checkout, Secret scan (gitleaks), Build, SAST (bandit), Dependency scan (pip-audit), Tests, Integration (network isolation check). All reports are archived as build artifacts, also when a stage is unstable. There are no gate rules yet; failing scans mark the stage UNSTABLE but do not fail the build (that is SKOLE-28).

## 1. Start Jenkins in Docker (macOS, Docker Desktop, Apple Silicon)

The pipeline runs `docker` commands, so Jenkins needs a Docker client inside the container plus access to the host Docker daemon. The stock `jenkins/jenkins` image has no Docker client, and installing one with `apt` needs outbound HTTP to `deb.debian.org`, which some networks block. Instead, a small custom image bakes in a pinned static Docker CLI and the Compose plugin, downloaded over HTTPS. This also means the binaries survive when the container is recreated.

### The custom image

The image is defined in [jenkins/Dockerfile](../jenkins/Dockerfile). It:

- starts from `jenkins/jenkins:lts-jdk17`;
- downloads the static Docker CLI from `download.docker.com` and the Compose plugin from GitHub releases, both pinned (`DOCKER_VERSION`, `COMPOSE_VERSION`), using the container's own architecture (`uname -m`, i.e. `aarch64` on Apple Silicon) — not the host's;
- uses an entrypoint ([jenkins/entrypoint.sh](../jenkins/entrypoint.sh)) that, at start-up, reads the group of the mounted Docker socket **inside the container** and gives the `jenkins` user access to it, then runs Jenkins as `jenkins`. No host group ID is read.

Build it:

```bash
docker build -t car-valuation-jenkins:local jenkins/
```

### The Docker socket on Docker Desktop

Docker Desktop on macOS does not create `/var/run/docker.sock` on the host. The real socket is under your home directory. Find it:

```bash
docker context inspect --format '{{.Endpoints.docker.Host}}'
```

It prints something like `unix:///Users/<you>/.docker/run/docker.sock`. Mount that path into the container at `/var/run/docker.sock`. The command below uses `$HOME/.docker/run/docker.sock`, which is the default.

### JENKINS_HOME must be a shared path with the same value on host and container

The pipeline runs `docker` commands that bind-mount the workspace (for example `-v $WORKSPACE:/src`) and relative paths from `docker compose` (for example `./secrets`). These mounts are interpreted by the **host** Docker daemon (Docker Desktop), not by the Jenkins container. So the workspace must sit at a path that exists, with the same spelling, on the host.

If Jenkins stores its workspace at the image default `/var/jenkins_home/workspace/...`, that path does not exist on the host, and the host daemon mounts an empty directory. That is what caused build #1 to fail (`gitleaks: not a git repository`, `build_carreport.sh: Directory '/tmp/carreport' is not installable`).

The fix: put `JENKINS_HOME` on a host directory bind-mounted at the **same path** inside the container. Here that is `$HOME/jenkins_home` (i.e. `/Users/<you>/jenkins_home`). `$HOME` is under `/Users`, which Docker Desktop shares by default, so no extra file-sharing setup is needed.

### Run the container

```bash
mkdir -p "$HOME/jenkins_home" && chmod 777 "$HOME/jenkins_home"
```

```bash
docker run -d --name jenkins \
  -p 8080:8080 -p 50000:50000 \
  -e JENKINS_HOME="$HOME/jenkins_home" \
  -v "$HOME/jenkins_home:$HOME/jenkins_home" \
  -v "$HOME/.docker/run/docker.sock:/var/run/docker.sock" \
  car-valuation-jenkins:local
```

The bind mount uses the identical path on both sides (`$HOME/jenkins_home:$HOME/jenkins_home`), and `JENKINS_HOME` points at it. The workspace then lives at `$HOME/jenkins_home/workspace/<job>` on both host and container, so nested `docker run -v` and compose bind mounts resolve to real host files. Do not use `--volumes-from`: it would not make the compose bind mounts work.

No `--group-add` is needed: the entrypoint fixes socket access from inside the container. On Docker Desktop the mounted socket is owned by `root:root` (mode 660), so the entrypoint adds `jenkins` to the `root` group; on a daemon where the socket has a non-zero group, it creates a matching `dockerhost` group instead.

### Verify Docker and path sharing work inside the container

```bash
docker exec jenkins docker ps
```

```bash
docker exec jenkins docker compose version
```

Confirm a nested bind mount sees the same host path (this is the thing that was broken):

```bash
docker exec jenkins bash -c 'd="$JENKINS_HOME/workspace/mounttest"; mkdir -p "$d"; echo ok > "$d/proof.txt"; docker run --rm -v "$d:/mnt" alpine:3.20 cat /mnt/proof.txt; rm -rf "$d"'
```

The `docker ps` lists running containers (you will see `jenkins` itself); `docker compose version` prints `Docker Compose version v2.29.7`; the mount test prints `ok`. All three were verified working with this setup.

### Finish first-run setup

Get the admin password and open Jenkins:

```bash
docker exec jenkins cat "$HOME/jenkins_home/secrets/initialAdminPassword"
```

Open http://localhost:8080, paste the password, install the suggested plugins, and create the admin user. Make sure the **Pipeline**, **Git**, and **JUnit** plugins are installed (the suggested set includes them).

Because `JENKINS_HOME` moved to `$HOME/jenkins_home`, this is a fresh Jenkins home. Redo the one-time UI setup described below (the `github-token` credential and the `car-valuation` multibranch job).

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
