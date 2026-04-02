output "cluster_name" {
  description = "GKE cluster name for gcloud get-credentials"
  value       = module.gke.cluster_name
}

output "cluster_endpoint" {
  value     = module.gke.cluster_endpoint
  sensitive = true
}

output "artifact_registry_url" {
  description = "Docker image base URL: {region}-docker.pkg.dev/{project}/mlops-docker"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${module.artifact_registry.repository_id}"
}

output "model_bucket" {
  value = module.storage.model_bucket_name
}

output "mlflow_bucket" {
  value = module.storage.mlflow_bucket_name
}

output "data_bucket" {
  value = module.storage.data_bucket_name
}
