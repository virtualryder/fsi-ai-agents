output "state_machine_arn" {
  value = aws_sfn_state_machine.docintel.arn
}

output "hitl_table" {
  value = aws_dynamodb_table.hitl.name
}

output "lambda_function_names" {
  value = [for f in aws_lambda_function.node : f.function_name]
}
