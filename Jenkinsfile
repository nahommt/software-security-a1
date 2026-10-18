pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        COMPOSE_PROJECT_NAME = 'assignment1'
        PY_IMAGE = 'python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
        GITLEAKS_IMAGE = 'zricethezav/gitleaks:v8.18.4'
        BANDIT_VERSION = '1.8.6'
        PIP_AUDIT_VERSION = '2.7.3'
        SERVICES = 'auth-gateway car-service report-service'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'mkdir -p reports && chmod 777 reports'
            }
        }

        stage('Secret scan') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        docker run --rm -v "$WORKSPACE:/repo" ${GITLEAKS_IMAGE} \
                            detect --source=/repo \
                            --report-format json --report-path /repo/reports/gitleaks.json --redact
                    '''
                }
            }
        }

        stage('Build') {
            steps {
                sh '''
                    ./scripts/generate_secrets.sh
                    ./scripts/build_carreport.sh
                    docker compose build
                    docker compose --profile test build
                '''
            }
        }

        stage('SAST') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        docker run --rm -v "$WORKSPACE:/src" -w /src ${PY_IMAGE} sh -c '
                            pip install --quiet bandit=='"${BANDIT_VERSION}"' &&
                            for svc in '"${SERVICES}"'; do
                                bandit -r "/src/$svc/app" -f json -o "/src/reports/bandit-$svc.json" || true
                                bandit -r "/src/$svc/app" -f txt  -o "/src/reports/bandit-$svc.txt"  || true
                            done
                        '
                    '''
                }
            }
        }

        stage('Dependency scan') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        docker run --rm -v "$WORKSPACE:/src" -w /src ${PY_IMAGE} sh -c '
                            pip install --quiet pip-audit=='"${PIP_AUDIT_VERSION}"' &&
                            for svc in '"${SERVICES}"'; do
                                for req in "/src/$svc/requirements.txt" "/src/$svc/requirements-dev.txt"; do
                                    [ -f "$req" ] || continue
                                    name="$svc-$(basename "$req" .txt)"
                                    pip-audit -r "$req" -f json -o "/src/reports/pip-audit-$name.json" || true
                                done
                            done
                        '
                    '''
                }
            }
        }

        stage('Tests') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        for svc in ${SERVICES}; do
                            docker run --rm --network none \
                                -v "$WORKSPACE/reports:/reports" \
                                "assignment1-${svc}-test:latest" \
                                python -m pytest -q -p no:cacheprovider \
                                --junitxml="/reports/junit-${svc}.xml" || true
                        done
                    '''
                }
            }
        }

        stage('Integration') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        docker compose down -v || true
                        ./scripts/seed.sh
                        docker compose up -d
                        sleep 5

                        docker compose exec -T report-service python -c "import socket,sys
reach={}
for host in ('car-service','auth-gateway'):
    try:
        socket.create_connection((host,8000),3).close(); reach[host]=True
    except Exception:
        reach[host]=False
print('report-service -> car-service reachable:', reach['car-service'])
print('report-service -> auth-gateway reachable:', reach['auth-gateway'])
ok = reach['car-service'] and not reach['auth-gateway']
print('T14 network isolation holds:', ok)
sys.exit(0 if ok else 1)" | tee reports/integration-network.txt
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker compose down -v || true'
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true, fingerprint: true
            junit testResults: 'reports/junit-*.xml', allowEmptyResults: true
        }
    }
}
