provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  # Single naming prefix used by all modules — matches .env.example contract
  name_prefix = var.project_id
}

module "vpc" {
  source = "./modules/vpc"

  project_id  = var.project_id
  region      = var.region
  name_prefix = local.name_prefix
  labels      = var.labels
}

module "gke" {
  source = "./modules/gke"

  project_id  = var.project_id
  region      = var.region
  zone        = var.zone
  name_prefix = local.name_prefix
  environment = var.environment
  labels      = var.labels

  network_id    = module.vpc.network_id
  subnet_id     = module.vpc.subnet_id
  pod_range     = module.vpc.pod_range_name
  service_range = module.vpc.service_range_name
  master_cidr   = "172.16.0.0/28"

  authorized_networks = var.authorized_networks

  enable_gpu_training_pool      = var.enable_gpu_training_pool
  gpu_training_machine_type     = var.gpu_training_machine_type
  gpu_training_accelerator_type = var.gpu_training_accelerator_type

  enable_gpu_inference_pool      = var.enable_gpu_inference_pool
  gpu_inference_machine_type     = var.gpu_inference_machine_type
  gpu_inference_accelerator_type = var.gpu_inference_accelerator_type
}

module "iam" {
  source = "./modules/iam"

  project_id  = var.project_id
  name_prefix = local.name_prefix

  # Workload Identity bindings: KSA names must match what Helm charts create
  workload_identity_bindings = {
    airflow = {
      namespace            = "ml-platform"
      service_account_name = "airflow-worker"
    }
    mlflow = {
      namespace            = "ml-platform"
      service_account_name = "mlflow"
    }
    inference = {
      namespace            = "ml-inference"
      service_account_name = "llm-serving"
    }
    monitoring = {
      namespace            = "monitoring"
      service_account_name = "kube-prometheus-stack-prometheus"
    }
  }
}

module "artifact_registry" {
  source = "./modules/artifact-registry"

  project_id = var.project_id
  region     = var.region
  # Fixed repo name "mlops-docker" — matches CI image push path and DAG image refs
  repo_id = "mlops-docker"
  labels  = var.labels
}

module "storage" {
  source = "./modules/storage"

  project_id  = var.project_id
  region      = var.region
  name_prefix = local.name_prefix
  labels      = var.labels

  airflow_gsa_email   = module.iam.service_account_emails["airflow"]
  mlflow_gsa_email    = module.iam.service_account_emails["mlflow"]
  inference_gsa_email = module.iam.service_account_emails["inference"]
}
