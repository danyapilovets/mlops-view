variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Artifact Registry location (e.g. europe-west1)."
}

variable "repo_id" {
  type        = string
  description = "Repository ID; use mlops-docker."
  default     = "mlops-docker"

  validation {
    condition     = var.repo_id == "mlops-docker"
    error_message = "repo_id must be the fixed value mlops-docker."
  }
}

variable "labels" {
  type        = map(string)
  description = "Labels applied to the repository."
  default     = {}
}
