output "state_machine_arn" {
  value = aws_sfn_state_machine.collections.arn
}

output "hitl_table" {
  value = aws_dynamodb_table.hitl.name
}
