variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region for the regional cluster."
}

variable "zone" {
  type        = string
  description = "GCP zone within var.region; GPU node pools use this as node_locations."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for cluster and node pool resource names."
}

variable "environment" {
  type        = string
  description = "Environment name (e.g. prod, staging)."
}

variable "labels" {
  type        = map(string)
  description = "Labels applied to cluster and node pool resources."
  default     = {}
}

variable "network_id" {
  type        = string
  description = "VPC network ID or self link."
}

variable "subnet_id" {
  type        = string
  description = "Subnetwork ID or self link."
}

variable "pod_range" {
  type        = string
  description = "Secondary range name on the subnet for cluster pods."
}

variable "service_range" {
  type        = string
  description = "Secondary range name on the subnet for cluster services."
}

variable "master_cidr" {
  type        = string
  description = "RFC1918 /28 CIDR for the private control plane."
}

variable "authorized_networks" {
  type = list(object({
    display_name = string
    cidr_block   = string
  }))
  description = "CIDR blocks allowed to reach the public control plane endpoint."
  default     = []
}

variable "enable_gpu_training_pool" {
  type        = bool
  description = "Create the spot GPU training node pool (scale-to-zero)."
  default     = false
}

variable "gpu_training_machine_type" {
  type        = string
  description = "Machine type for the GPU training node pool."
  default     = "n1-standard-4"
}

variable "gpu_training_accelerator_type" {
  type        = string
  description = "Accelerator type for the GPU training node pool."
  default     = "nvidia-tesla-t4"
}

variable "enable_gpu_inference_pool" {
  type        = bool
  description = "Create the on-demand GPU inference node pool."
  default     = false
}

variable "gpu_inference_machine_type" {
  type        = string
  description = "Machine type for the GPU inference node pool."
  default     = "n1-standard-4"
}

variable "gpu_inference_accelerator_type" {
  type        = string
  description = "Accelerator type for the GPU inference node pool."
  default     = "nvidia-tesla-t4"
}
