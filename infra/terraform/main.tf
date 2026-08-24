resource "aws_s3_bucket" "lake" {
  bucket        = var.bucket_name
  force_destroy = false
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "transport" {
  bucket = aws_s3_bucket.lake.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
# Do not expire published tables or vectors by age alone. Retention must respect release references.
resource "aws_s3_bucket_lifecycle_configuration" "incomplete_uploads" {
  bucket = aws_s3_bucket.lake.id
  rule {
    id     = "abort-incomplete-multipart-only"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}
resource "aws_dynamodb_table" "delta_locks" {
  name         = "${var.bucket_name}-delta-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tablePath"
  range_key    = "fileName"
  attribute {
    name = "tablePath"
    type = "S"
  }
  attribute {
    name = "fileName"
    type = "S"
  }
  ttl {
    attribute_name = "expireTime"
    enabled        = true
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
  deletion_protection_enabled = true
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_policy" "writer" {
  name_prefix = "veritylake-writer-"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"], Resource = aws_s3_bucket.lake.arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], Resource = "${aws_s3_bucket.lake.arn}/*" },
      { Effect = "Allow", Action = ["dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query"], Resource = aws_dynamodb_table.delta_locks.arn }
    ]
  })
}
resource "aws_iam_policy" "reader" {
  name_prefix = "veritylake-reader-"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.lake.arn}/catalog/*" }]
  })
}
resource "aws_iam_role_policy_attachment" "writer" {
  count      = var.writer_role_name == null ? 0 : 1
  role       = var.writer_role_name
  policy_arn = aws_iam_policy.writer.arn
}
resource "aws_iam_role_policy_attachment" "reader" {
  count      = var.reader_role_name == null ? 0 : 1
  role       = var.reader_role_name
  policy_arn = aws_iam_policy.reader.arn
}
