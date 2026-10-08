# Read-only diagnostics: stack events, recent Lambda logs, state machine runs.
param([string]$Region = 'ap-south-1', [string]$Stack = 'chhaon', [string]$What = 'events', [string]$Since = '15m')
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
switch ($What) {
    'events' {
        aws cloudformation describe-stack-events --region $Region --stack-name $Stack --max-items 30 --query "StackEvents[].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]" --output text
    }
    'logs' {
        $fns = aws cloudformation describe-stack-resources --region $Region --stack-name $Stack --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text
        foreach ($f in ($fns -split '\s+' | Where-Object { $_ })) {
            Write-Output "===== $f"
            aws logs tail "/aws/lambda/$f" --region $Region --since $Since --format short 2>&1 | Select-Object -Last 60
        }
    }
    'runs' {
        $sm = aws cloudformation describe-stacks --region $Region --stack-name $Stack --query "Stacks[0].Outputs[?OutputKey=='ProtocolStateMachineArn'].OutputValue" --output text
        aws stepfunctions list-executions --region $Region --state-machine-arn $sm --max-results 10 --query "executions[].[name,status,startDate]" --output text
    }
    'schedules' {
        $g = aws cloudformation describe-stacks --region $Region --stack-name $Stack --query "Stacks[0].Outputs[?OutputKey=='ScheduleGroupName'].OutputValue" --output text
        aws scheduler list-schedules --region $Region --group-name $g --query "Schedules[].[Name,State]" --output text
    }
}
exit 0
