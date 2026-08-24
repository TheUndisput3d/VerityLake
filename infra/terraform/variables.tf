variable "region" {
  type    = string
  default = "us-east-1"
}
variable "environment" {
  type    = string
  default = "portfolio"
}
variable "bucket_name" {
  type        = string
  description = "Globally unique existing-DNS-compatible name. No personal or secret information."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Use 3-63 lowercase letters, digits and hyphens."
  }
}
variable "writer_role_name" {
  type        = string
  default     = null
  description = "Optional existing IAM role name for ingestion. Trust policy is managed separately."
}
variable "reader_role_name" {
  type        = string
  default     = null
  description = "Optional existing IAM role name for API catalog-only access."
}
