project_id  = "mlops-platform-dev"
region      = "us-central1"
zone        = "us-central1-a"
environment = "dev"

enable_gpu_training_pool  = true
enable_gpu_inference_pool = true

authorized_networks = [
  {
    display_name = "dev-access"
    cidr_block   = "0.0.0.0/0"
  }
]

labels = {
  environment = "dev"
  team        = "mlops"
  cost_center = "ml-platform"
}
