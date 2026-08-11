# Import existing, already-created Azure resources into Terraform state.
# These are the ONLY resources this configuration manages — no AKS, no
# resource group, no networking, nothing else.
#
# Workflow:
#   1. terraform plan -generate-config-out=generated.tf
#   2. Review generated.tf carefully, then move/clean up the resource blocks
#      into main.tf (adding lifecycle.prevent_destroy along the way).
#   3. terraform apply — this should show 0 to destroy. If it proposes any
#      destructive change, STOP and investigate before proceeding.

import {
  to = azurerm_cognitive_account.kubebot
  id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/${var.cognitive_account_name}"
}

import {
  to = azurerm_cognitive_deployment.gpt_4_1_mini
  id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/${var.cognitive_account_name}/deployments/gpt-4.1-mini"
}

import {
  to = azurerm_cognitive_deployment.text_embedding_3_small
  id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/${var.cognitive_account_name}/deployments/text-embedding-3-small"
}
