.PHONY: help validate lint test up down build-all kubeconfig

PYTHON := $(shell if [ -x ".venv/bin/python3" ]; then echo ".venv/bin/python3"; else echo "python3"; fi)

help: ## Показати цю довідку
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Terraform ---

tf-init: ## terraform init з GCS backend (dev)
	cd terraform && terraform init -backend-config="bucket=$${TF_STATE_BUCKET:-mlops-platform-dev-terraform-state}"

tf-plan: ## terraform plan (dev)
	cd terraform && terraform plan -var-file=environments/dev.tfvars

tf-apply: ## terraform apply (dev)
	cd terraform && terraform apply -var-file=environments/dev.tfvars

# --- Валідація ---

validate: ## Валідація маніфестів (kustomize + kubeconform + helm lint)
	./scripts/validate.sh

lint: ## Лінтинг Python + Shell + Dockerfile
	@echo "==> ruff"
	ruff check .
	@echo "==> shellcheck"
	shellcheck scripts/*.sh
	@echo "==> hadolint"
	@for f in docker/training/Dockerfile docker/inference/Dockerfile docker/pipeline-runner/Dockerfile monitoring/exporters/Dockerfile; do \
		echo "  $$f"; hadolint "$$f"; \
	done

test: ## Запуск тестів (pytest)
	$(PYTHON) -m pytest tests/ -v

# --- Docker ---

build-training: ## Збірка training image
	docker build -t mlops-docker/training:latest -f docker/training/Dockerfile docker/training/

build-inference: ## Збірка inference image
	docker build -t mlops-docker/inference:latest -f docker/inference/Dockerfile docker/inference/

build-all: build-training build-inference ## Збірка всіх images

# --- Локальна розробка ---

up: ## Запуск docker-compose
	docker compose up -d

down: ## Зупинка docker-compose
	docker compose down

logs: ## Логи docker-compose
	docker compose logs -f

# --- Kubernetes ---

kubeconfig: ## Отримати kubeconfig для GKE кластера
	gcloud container clusters get-credentials $${GKE_CLUSTER_NAME:-mlops-platform-dev-gke} \
		--region $${GCP_REGION:-us-central1} \
		--project $${GCP_PROJECT_ID:-mlops-platform-dev}

# --- Flux ---

flux-reconcile: ## Примусова синхронізація Flux
	flux reconcile source git flux-system
	flux reconcile kustomization flux-system

# --- Ansible ---

bootstrap: ## Bootstrap GKE кластера (Flux + GitOps)
	cd ansible && ansible-playbook playbooks/bootstrap-cluster.yaml -i inventories/dev/hosts.yaml

# --- Очищення ---

clean: ## Видалення кешів та артефактів
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
