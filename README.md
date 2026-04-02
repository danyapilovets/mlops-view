# mlops-view

Інфраструктура для запуску LLM у продакшені на GKE. Репозиторій покриває весь шлях: від створення хмарних ресурсів до деплою моделі, моніторингу і автоматичного fine-tuning.

## Ідея

Є модель (Llama 2 7B). Потрібно її дотренувати на своїх даних, задеплоїти як API і слідкувати за якістю. І щоб це все відтворювалось одним `terraform apply` + `git push`, а не ручними kubectl-ами.

Тому тут GitOps: Flux CD дивиться на цей репо і тримає кластер у синхроні з кодом. Ніхто не робить `helm upgrade` руками — все через PR.

## Як це працює

Якщо коротко — три шари:

**1. Terraform створює GCP-ресурси**

VPC з приватною підмережею, GKE кластер з GPU нод-пулами (T4 для inference, A100 Spot для тренування), Artifact Registry для Docker-образів, GCS бакети для моделей/артефактів, IAM з Workload Identity (поди автентифікуються як GCP Service Accounts, ніяких JSON-ключів).

```bash
make tf-init && make tf-plan && make tf-apply
```

**2. Flux CD підхоплює кластер і деплоїть все**

Після bootstrap (через Ansible або `make bootstrap`) Flux починає дивитись на `clusters/dev/` в цьому репо. Звідти він по ланцюжку підтягує:
- `clusters/base/` — неймспейси, ResourceQuota, LimitRange
- `tools/` — kube-prometheus-stack, External Secrets Operator, NVIDIA GPU Operator
- `apps/` — HelmRelease-и для vLLM, Airflow, MLflow, API Gateway

Кожен environment (dev/staging/prod) — це overlay з власним `cluster-vars` ConfigMap. Flux підставляє `${gcp_project}`, `${environment}` в маніфести через postBuild substitution.

**3. Додатки працюють на кластері**

- **vLLM** — inference сервер з OpenAI-compatible API, крутиться на GPU нодах, HPA за навантаженням
- **Airflow** — оркеструє пайплайни: fine-tuning → evaluation → promotion моделі в MLflow
- **MLflow** — experiment tracking + model registry
- **Prometheus + Grafana** — метрики з кожного компоненту, алерти на latency/GPU/failures

## Чому така структура

```
terraform/     — хмарна інфра
clusters/      — що Flux має деплоїти (per-environment)
tools/         — "платформні" компоненти (prometheus, ESO, GPU operator)
apps/          — бізнес-додатки (vLLM, Airflow, MLflow)
helm/          — кастомні чарти для того, чого немає готового
docker/        — образи, які збирає CI
pipelines/     — Airflow DAGs
monitoring/    — алерти, дашборди, custom exporter
ansible/       — bootstrap автоматизація
```

**`terraform/`** — окремо від Kubernetes-маніфестів, бо lifecycles різні. Інфра змінюється рідко, маніфести — часто. Terraform state живе в GCS.

**`clusters/base/` → `clusters/{env}/`** — overlay-структура Flux. Base описує що деплоїти, env — з якими параметрами. Додаєш staging — копіюєш dev, змінюєш ConfigMap.

**`tools/` vs `apps/`** — навмисний поділ. Tools — те, від чого залежать apps (prometheus, secrets, GPU drivers). Apps — бізнес-навантаження. Flux деплоїть tools раніше через `dependsOn`.

**`helm/`** — три кастомні чарти: `llm-serving` (vLLM з GPU affinity, tolerations, ServiceMonitor), `ml-gateway` (nginx з rate limiting), `grafana-dashboards` (provisioning через sidecar). Для Airflow і MLflow використовуються upstream чарти.

**`docker/`** — три образи. `inference` — vLLM + скрипт який тягне модель з GCS перед стартом. `training` — PyTorch + DeepSpeed + LoRA. `pipeline-runner` — легкий образ для Airflow задач (benchmark, eval).

**`ansible/`** — тут одне питання: "навіщо Ansible, якщо є Terraform і Flux?". Terraform створює кластер, але не може поставити Flux (це kubectl + flux bootstrap). Flux не може поставити сам себе. Ansible заповнює цей gap — роль `gke-bootstrap` ставить Flux, створює initial namespaces, і далі Flux бере на себе все інше. Це одноразова операція при створенні кластера.

**`monitoring/`** — PrometheusRule алерти (GPU utilization, inference latency, Airflow DAG failures), Grafana дашборди в JSON, і custom Python exporter який бере сирі метрики vLLM і рахує бізнес-метрики.

## CI/CD

П'ять GitHub Actions workflows:

- **ci** — на кожен PR: terraform validate, helm lint, kubeconform, ruff, pytest, shellcheck, hadolint. Якщо щось червоне — PR не мержиться.
- **build-images** — збирає Docker-образи при змінах у `docker/`, пушить в Artifact Registry, сканує Trivy.
- **deploy-infra** — terraform plan/apply через Workload Identity Federation (OIDC, без ключів).
- **flux-sync** — на push в main анотує Flux GitRepository для негайної синхронізації.
- **deploy-model** — ручний trigger для canary-деплою нової моделі з перевіркою через Prometheus.
## Локальна розробка

```bash
make up    # postgres + mlflow + prometheus + grafana
make test  # pytest (імпорт DAGs, парсинг метрик)
make lint  # ruff + shellcheck + hadolint
```

docker-compose піднімає локальну копію моніторингу і MLflow для розробки DAGs і дашбордів без кластера.
