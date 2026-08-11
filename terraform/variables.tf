variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Azure tenant ID."
  type        = string
  sensitive   = true
}

variable "resource_group_name" {
  description = "Resource group containing the Foundry account."
  type        = string
}

variable "cognitive_account_name" {
  description = "Name of the Foundry account."
  type        = string
}

variable "location" {
  description = "Azure region for the Foundry account."
  type        = string
  default     = "westus"
}
