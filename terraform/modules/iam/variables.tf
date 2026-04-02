variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for service account account_id values (must yield valid 6–30 char account IDs with each binding key)."
}

variable "workload_identity_bindings" {
  type = map(object({
    namespace            = string
    service_account_name = string
  }))
  description = "Map key => Kubernetes service account to bind via Workload Identity."
}
