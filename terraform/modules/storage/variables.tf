variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCS bucket location (region)."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for bucket names; must be globally unique with suffixes."
}

variable "labels" {
  type        = map(string)
  description = "Labels applied to all buckets."
  default     = {}
}

variable "airflow_gsa_email" {
  type        = string
  description = "Airflow Google service account email (objectViewer on data and dags)."
}

variable "mlflow_gsa_email" {
  type        = string
  description = "MLflow Google service account email (objectAdmin on mlflow bucket)."
}

variable "inference_gsa_email" {
  type        = string
  description = "Inference Google service account email (objectAdmin on models bucket)."
}
