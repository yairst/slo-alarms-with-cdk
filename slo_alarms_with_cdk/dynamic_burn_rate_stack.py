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

        update_thresh_name = "-".join(
            [
                'update-thresholds-of',
                update_thresh_env_vars['NAMESPACE'].replace('/','-'),
                update_thresh_env_vars['SLO_TYPE'],
                'SLO-alarms'
            ]
        )
        update_thresh = _lambda.Function(
            self, 'UpdateThresholds',
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='update_thresholds.lambda_handler',
            code=_lambda.Code.from_asset('lambda'),
            environment=update_thresh_env_vars,
            initial_policy=update_thresh_role_policy_statements,
            function_name=update_thresh_name
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

        update_n_slo_name = "-".join(
            [
                'update-Nslo-for',
                update_n_slo_env_vars['NAMESPACE'].replace('/','-'),
                update_n_slo_env_vars['SLO_TYPE'],
                'SLO-alarms'
            ]
        )
        update_n_slo_env_vars['UPDATE_THRESH_FUNC'] = update_thresh_name
        update_n_slo = _lambda.Function(
            self, 'UpdateNslo',
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='update_n_slo.lambda_handler',
            code=_lambda.Code.from_asset('lambda'),
            environment=update_n_slo_env_vars,
            initial_policy=update_n_slo_role_policy_statements,
            function_name=update_n_slo_name
        )

        for rate, minutes in sched_rates.items():
            duration = Duration.minutes(minutes)
            br_scheduler = events.Rule(
                self, "OnceEvery" + str(minutes) + "MinutesScheduler",
                schedule=events.Schedule.rate(duration),
                rule_name=rate + "BrOnceEvery" + str(minutes) + "MinutesScheduler"
            )
            br_scheduler.add_target(targets.LambdaFunction(update_thresh))

        n_slo_scheduler = events.Rule(
            self, "OnceADayScheduler",
            schedule=events.Schedule.rate(Duration.hours(24)),
            rule_name="OnceADayScheduler"
        )
        n_slo_scheduler.add_target(targets.LambdaFunction(update_n_slo))
