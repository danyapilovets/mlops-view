output "service_account_emails" {
  description = "Map of workload_identity_bindings key => Google service account email."
  value = {
    for k, sa in google_service_account.this : k => sa.email
  }
}
