variable "project_id" {
  description = "GCP project ID — used as naming prefix everywhere"
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod."
  }
}

variable "enable_gpu_training_pool" {
  type    = bool
  default = false
}

variable "enable_gpu_inference_pool" {
  type    = bool
  default = false
}

variable "gpu_training_machine_type" {
  type    = string
  default = "n1-standard-8"
}

variable "gpu_training_accelerator_type" {
  type    = string
  default = "nvidia-tesla-t4"
}

variable "gpu_inference_machine_type" {
  type    = string
  default = "n1-standard-8"
}

variable "gpu_inference_accelerator_type" {
  type    = string
  default = "nvidia-tesla-t4"
}

variable "authorized_networks" {
  type = list(object({
    display_name = string
    cidr_block   = string
  }))
  default = []
}

variable "labels" {
  type    = map(string)
  default = {}
}
