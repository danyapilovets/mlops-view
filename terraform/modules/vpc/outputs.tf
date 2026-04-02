output "network_id" {
  value = google_compute_network.vpc.id
}

output "network_name" {
  value = google_compute_network.vpc.name
}

output "subnet_id" {
  value = google_compute_subnetwork.subnet.id
}

output "subnet_name" {
  value = google_compute_subnetwork.subnet.name
}

output "pod_range_name" {
  value = "pods"
}

output "service_range_name" {
  value = "services"
}
