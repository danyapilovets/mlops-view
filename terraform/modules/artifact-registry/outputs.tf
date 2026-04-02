output "repository_id" {
  description = "Artifact Registry repository_id (mlops-docker)."
  value       = var.repo_id
}

output "repository_url" {
  description = "Docker registry host/path for this repository."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repo_id}"
}
