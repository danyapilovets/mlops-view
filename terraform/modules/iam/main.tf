terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

resource "google_service_account" "this" {
  for_each = var.workload_identity_bindings

  project      = var.project_id
  account_id   = substr("${var.name_prefix}-${each.key}", 0, 30)
  display_name = "${var.name_prefix}-${each.key}"
}

resource "google_service_account_iam_member" "workload_identity" {
  for_each = var.workload_identity_bindings

  service_account_id = google_service_account.this[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value.namespace}/${each.value.service_account_name}]"
}
