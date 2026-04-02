terraform {
  backend "gcs" {
    prefix = "terraform/state"
    # bucket is passed via:
    #   CLI:  terraform init -backend-config="bucket=mlops-platform-dev-terraform-state"
    #   CI:   -backend-config="bucket=${{ vars.TF_STATE_BUCKET }}"
  }
}
