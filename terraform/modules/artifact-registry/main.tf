terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

resource "google_artifact_registry_repository" "docker" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repo_id
  format        = "DOCKER"
  labels        = var.labels

  cleanup_policies {
    id     = "delete-untagged-after-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }

  cleanup_policies {
    id     = "keep-10-most-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
}
