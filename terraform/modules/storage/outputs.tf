output "model_bucket_name" {
  description = "GCS bucket name for model artifacts."
  value       = google_storage_bucket.models.name
}

output "data_bucket_name" {
  description = "GCS bucket name for data (Airflow viewer)."
  value       = google_storage_bucket.data.name
}

output "mlflow_bucket_name" {
  description = "GCS bucket name for MLflow artifacts."
  value       = google_storage_bucket.mlflow.name
}

output "dags_bucket_name" {
  description = "GCS bucket name for Airflow DAGs."
  value       = google_storage_bucket.dags.name
}
