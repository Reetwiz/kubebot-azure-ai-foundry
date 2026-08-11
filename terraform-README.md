# Terraform - Azure AI Foundry

This configuration manages **only** the Azure AI Foundry (Cognitive Services)
account that backs kubebot's chat + embedding models, and its model
deployments. It deliberately does **not** manage AKS, resource groups,
networking, or anything else. Treat it as an example and review every plan.

## What's managed here

| Resource | Address | Notes |
|---|---|---|
| Cognitive Services (AI Foundry) account | `azurerm_cognitive_account.kubebot` | Existing resource, imported (not created) by Terraform. `kind = AIServices`. |
| Chat model deployment (mini) | `azurerm_cognitive_deployment.gpt_4_1_mini` | Existing, imported. |
| Embedding model deployment | `azurerm_cognitive_deployment.text_embedding_3_small` | Existing, imported. |
| Chat model deployment (standard) | `azurerm_cognitive_deployment.gpt_4_1` | Created **by** Terraform (not imported) as a proof that Terraform can safely add new capacity. Matches the `standard` label in `AZURE_OPENAI_CHAT_DEPLOYMENTS`. |

Every resource above has `lifecycle { prevent_destroy = true }`. This makes it
prevent accidental deletion through normal plans without first removing that block. This is a deliberate guardrail since
this account backs a live application.

**`terraform destroy` should never be run against this configuration.**

## Remote state backend

The backend block is intentionally empty so no environment names are committed.
Create a private Azure Storage Account and pass its values during initialization:

```bash
terraform init \
  -backend-config="resource_group_name=<state-resource-group>" \
  -backend-config="storage_account_name=<state-storage-account>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=kubebot-foundry.tfstate" \
  -backend-config="use_azuread_auth=true"
```

Locking is provided natively by Azure Blob leases (no separate lock table
needed). Auth uses the caller's Azure AD identity (`use_azuread_auth = true`
in [versions.tf](versions.tf)) rather than a shared storage account key, so no
secret needs to be distributed to run Terraform. The caller requires the
`Storage Blob Data Contributor` role on the state Storage Account.

## Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in your subscription/tenant IDs
terraform init -backend-config=<your-backend-config-file>
terraform plan     # review carefully — should show 0 to destroy
terraform apply
```

`subscription_id` and `tenant_id` come from `terraform.tfvars`, which is
gitignored and never committed — only the placeholder
[terraform.tfvars.example](terraform.tfvars.example) is tracked. Terraform
picks up `terraform.tfvars` automatically, no extra flag needed. This is
still a single-environment example, not a complete environment strategy.

## How the existing resources were imported

Rather than hand-writing resource blocks and risking drift/mismatches against
real Azure state, the 3 pre-existing resources were imported using Terraform
1.5+ `import` blocks (see [import.tf](import.tf)) combined with
`terraform plan -generate-config-out=generated.tf` to auto-generate accurate
resource configuration from the real infrastructure, which was then reviewed,
cleaned up, and folded into [main.tf](main.tf) (adding `prevent_destroy` and
tags along the way).

## Safety notes

- The `azurerm` provider's `cognitive_account` feature flag
  `purge_soft_delete_on_destroy` is explicitly set to `false` in
  [providers.tf](providers.tf) — a second layer of protection alongside
  `prevent_destroy`.
- Every `terraform plan` should be reviewed for `0 to destroy` before running
  `apply`. If a plan ever proposes deleting/replacing the Cognitive account or
  either existing deployment, **stop and investigate** — that indicates
  configuration drift, not something to apply blindly.
- This account may directly back a live application. Assume any
  destructive change here breaks it immediately for real users.
