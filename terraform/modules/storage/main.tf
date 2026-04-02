terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

locals {
  bucket_names = {
    models = "${var.name_prefix}-models"
    data   = "${var.name_prefix}-data"
    mlflow = "${var.name_prefix}-mlflow"
    dags   = "${var.name_prefix}-dags"
  }
}

resource "google_storage_bucket" "models" {
  name                        = local.bucket_names.models
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = 90
    }
  }
}

resource "google_storage_bucket" "data" {
  name                        = local.bucket_names.data
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = var.labels
}

resource "google_storage_bucket" "mlflow" {
  name                        = local.bucket_names.mlflow
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = var.labels
}

resource "google_storage_bucket" "dags" {
  name                        = local.bucket_names.dags
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = var.labels
}

resource "google_storage_bucket_iam_member" "models_inference_admin" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.inference_gsa_email}"
}

resource "google_storage_bucket_iam_member" "data_airflow_viewer" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.airflow_gsa_email}"
}

resource "google_storage_bucket_iam_member" "mlflow_mlflow_admin" {
  bucket = google_storage_bucket.mlflow.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.mlflow_gsa_email}"
}

resource "google_storage_bucket_iam_member" "dags_airflow_viewer" {
  bucket = google_storage_bucket.dags.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.airflow_gsa_email}"
}
