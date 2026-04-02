terraform {
  required_providers {
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.0"
    }
  }
}

locals {
  resource_labels = merge(var.labels, { environment = var.environment })
}

resource "google_container_cluster" "this" {
  provider = google-beta

  name     = "${var.name_prefix}-gke"
  location = var.region
  project  = var.project_id

  remove_default_node_pool = true
  initial_node_count       = 1

  network    = var.network_id
  subnetwork = var.subnet_id

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pod_range
    services_secondary_range_name = var.service_range
  }

  dynamic "master_authorized_networks_config" {
    for_each = length(var.authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.authorized_networks
        content {
          display_name = cidr_blocks.value.display_name
          cidr_block   = cidr_blocks.value.cidr_block
        }
      }
    }
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
    network_policy_config {
      disabled = false
    }
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
  }

  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
    managed_prometheus {
      enabled = true
    }
  }

  maintenance_policy {
    recurring_window {
      start_time = "1970-01-01T04:00:00Z"
      end_time   = "1970-01-01T08:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }

  resource_labels = local.resource_labels
}

resource "google_container_node_pool" "default" {
  provider = google-beta

  name     = "${var.name_prefix}-default"
  location = var.region
  cluster  = google_container_cluster.this.name
  project  = var.project_id

  autoscaling {
    min_node_count = 1
    max_node_count = 5
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-balanced"

    labels = local.resource_labels

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

resource "google_container_node_pool" "gpu_training" {
  count = var.enable_gpu_training_pool ? 1 : 0

  provider = google-beta

  name           = "${var.name_prefix}-gpu-training"
  location       = var.region
  node_locations = [var.zone]
  cluster        = google_container_cluster.this.name
  project        = var.project_id

  initial_node_count = 0

  autoscaling {
    min_node_count = 0
    max_node_count = 4
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.gpu_training_machine_type
    disk_size_gb = 100
    disk_type    = "pd-balanced"
    spot         = true

    labels = merge(local.resource_labels, { node_pool = "gpu-training" })

    guest_accelerator {
      type  = var.gpu_training_accelerator_type
      count = 1
      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }

    taint {
      key    = "nvidia.com/gpu"
      value  = "training"
      effect = "NO_SCHEDULE"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}

resource "google_container_node_pool" "gpu_inference" {
  count = var.enable_gpu_inference_pool ? 1 : 0

  provider = google-beta

  name           = "${var.name_prefix}-gpu-inference"
  location       = var.region
  node_locations = [var.zone]
  cluster        = google_container_cluster.this.name
  project        = var.project_id

  initial_node_count = 1

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.gpu_inference_machine_type
    disk_size_gb = 100
    disk_type    = "pd-balanced"
    spot         = false

    labels = merge(local.resource_labels, { node_pool = "gpu-inference" })

    guest_accelerator {
      type  = var.gpu_inference_accelerator_type
      count = 1
      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }

    taint {
      key    = "nvidia.com/gpu"
      value  = "inference"
      effect = "NO_SCHEDULE"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}
