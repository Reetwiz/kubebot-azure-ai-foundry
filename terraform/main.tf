# Terraform-managed resources for the kubebot Azure AI Foundry backend.
#
# Scope is intentionally narrow: this configuration manages ONLY the
# Cognitive Services (AI Foundry) account and its two model deployments.
# It does NOT create/manage the resource group, AKS, networking, or anything
# else — those are managed manually / by other means.
#
# All three resources below were imported from real, already-existing Azure
# infrastructure (see import.tf) rather than created fresh, and each carries
# `prevent_destroy = true` as a guardrail against accidental deletion via
# `terraform destroy` or a resource replacement.

resource "azurerm_cognitive_account" "kubebot" {
  name                = var.cognitive_account_name
  resource_group_name = var.resource_group_name
  location            = var.location
  kind                = "AIServices"
  sku_name            = "S0"

  custom_subdomain_name = var.cognitive_account_name

  local_auth_enabled                 = true
  public_network_access_enabled      = true
  outbound_network_access_restricted = false
  dynamic_throttling_enabled         = false
  project_management_enabled         = true

  identity {
    type = "SystemAssigned"
  }

  network_acls {
    default_action = "Allow"
  }

  tags = {
    managed_by = "terraform"
    project    = "kubebot-poc"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_cognitive_deployment" "gpt_4_1_mini" {
  name                 = "gpt-4.1-mini"
  cognitive_account_id = azurerm_cognitive_account.kubebot.id

  model {
    format  = "OpenAI"
    name    = "gpt-4.1-mini"
    version = "2025-04-14"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 100
  }

  rai_policy_name        = "Microsoft.DefaultV2"
  version_upgrade_option = "OnceNewDefaultVersionAvailable"

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_cognitive_deployment" "text_embedding_3_small" {
  name                 = "text-embedding-3-small"
  cognitive_account_id = azurerm_cognitive_account.kubebot.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 500
  }

  rai_policy_name        = "Microsoft.DefaultV2"
  version_upgrade_option = "OnceNewDefaultVersionAvailable"

  lifecycle {
    prevent_destroy = true
  }
}

# NEW deployment (not imported — created fresh by Terraform). This is the
# "standard" (non-mini) chat model referenced by AZURE_OPENAI_CHAT_DEPLOYMENTS
# in the application's .env config, added purely additively to prove out the
# Terraform workflow without touching the existing imported resources.
resource "azurerm_cognitive_deployment" "gpt_4_1" {
  name                 = "gpt-4.1"
  cognitive_account_id = azurerm_cognitive_account.kubebot.id

  model {
    format  = "OpenAI"
    name    = "gpt-4.1"
    version = "2025-04-14"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  version_upgrade_option = "OnceNewDefaultVersionAvailable"

  lifecycle {
    prevent_destroy = true
  }
}
