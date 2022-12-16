from constructs import Construct
from aws_cdk import (
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    Duration
)

class DynamicBurnRateStack(Construct):

    def __init__(self, scope: Construct, id: str,
        update_thresh_env_vars: dict, update_n_slo_env_vars: dict, sched_rates: dict, **kwargs):
        super().__init__(scope, id, **kwargs)

        update_thresh_role_policy_statements = [
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricData",
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:PutMetricAlarm",  
                ],
                resources=["*"],
            )
        ] 

        update_thresh = _lambda.Function(
            self, 'UpdateThresholds',
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='update_thresholds.lambda_handler',
            code=_lambda.Code.from_asset('lambda'),
            environment=update_thresh_env_vars,
            initial_policy=update_thresh_role_policy_statements
        )

        update_n_slo_role_policy_statements = [
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricData",
                    "cloudwatch:DescribeAlarms",
                    "lambda:GetFunctionConfiguration",
                    "lambda:UpdateFunctionConfiguration" 
                ],
                resources=["*"],
            )
        ]

        update_thresh_func_name = update_thresh.function_name
        update_n_slo_env_vars['UPDATE_THRESH_FUNC'] = update_thresh_func_name

        update_n_slo = _lambda.Function(
            self, 'UpdateNslo',
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='update_n_slo.lambda_handler',
            code=_lambda.Code.from_asset('lambda'),
            environment=update_n_slo_env_vars,
            initial_policy=update_n_slo_role_policy_statements
        )

        for rate in sched_rates.keys():
            br_scheduler = events.Rule(
                self, rate + "BrScheduler",
                schedule=events.Schedule.rate(sched_rates[rate])
            )
            br_scheduler.add_target(targets.LambdaFunction(update_thresh))

        n_slo_scheduler = events.Rule(
            self, "NsloScheduler",
            schedule=events.Schedule.rate(Duration.hours(24))
        )
        n_slo_scheduler.add_target(targets.LambdaFunction(update_n_slo))
