project_id  = "mlops-platform-prod"
region      = "us-central1"
zone        = "us-central1-a"
environment = "prod"

enable_gpu_training_pool  = true
enable_gpu_inference_pool = true

gpu_training_machine_type      = "n1-standard-16"
gpu_training_accelerator_type  = "nvidia-tesla-a100"
gpu_inference_machine_type     = "n1-standard-8"
gpu_inference_accelerator_type = "nvidia-tesla-t4"

authorized_networks = []

labels = {
  environment = "prod"
  team        = "mlops"
  cost_center = "ml-platform"
}
