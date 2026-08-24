output "bucket_name" { value = aws_s3_bucket.lake.id }
output "delta_lock_table" { value = aws_dynamodb_table.delta_locks.name }
output "writer_policy_arn" { value = aws_iam_policy.writer.arn }
output "reader_policy_arn" { value = aws_iam_policy.reader.arn }
output "region" { value = var.region }
