from constructs import Construct
from aws_cdk import (
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam
)

class DynamicBurnRateStack(Construct):

    def __init__(self, scope: Construct, id: str, env_vars: dict, sched_rates: dict, **kwargs):
        super().__init__(scope, id, **kwargs)

        role_policy_statements = [
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricData",
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:PutMetricAlarm",
                    "ssm:GetParameter"
                ],
                resources=["*"],
            )
        ] 

        update_thresh = _lambda.Function(
            self, 'UpdateThresholds',
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='update_thresholds.lambda_handler',
            code=_lambda.Code.from_asset('lambda'),
            environment=env_vars,
            initial_policy=role_policy_statements
        )

        for rate in sched_rates.keys():
            high_br_scheduler = events.Rule(
                self, rate + "BrScheduler",
                schedule=events.Schedule.rate(sched_rates[rate])
            )
            high_br_scheduler.add_target(targets.LambdaFunction(update_thresh))

