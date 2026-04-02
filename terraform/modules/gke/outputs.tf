output "cluster_name" {
  description = "GKE cluster name."
  value       = google_container_cluster.this.name
}

output "cluster_endpoint" {
  description = "Kubernetes API server endpoint."
  value       = google_container_cluster.this.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "Base64-encoded cluster CA certificate (master_auth)."
  value       = google_container_cluster.this.master_auth[0].cluster_ca_certificate
  sensitive   = true
}
