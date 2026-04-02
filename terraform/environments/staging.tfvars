project_id  = "mlops-platform-staging"
region      = "us-central1"
zone        = "us-central1-a"
environment = "staging"

enable_gpu_training_pool  = true
enable_gpu_inference_pool = true

gpu_training_accelerator_type  = "nvidia-tesla-t4"
gpu_inference_accelerator_type = "nvidia-tesla-t4"

authorized_networks = []

labels = {
  environment = "staging"
  team        = "mlops"
  cost_center = "ml-platform"
}
