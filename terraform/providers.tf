provider "azurerm" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  features {
    cognitive_account {
      # Do NOT purge the account's soft-deleted record on destroy. Combined
      # with prevent_destroy on the resource itself, this is a second layer
      # of protection against accidental data loss.
      purge_soft_delete_on_destroy = false
    }
  }
}
