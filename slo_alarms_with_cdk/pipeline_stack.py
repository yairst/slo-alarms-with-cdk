from constructs import Construct
from aws_cdk import (
    Stack,
    pipelines,
    aws_ssm as ssm,
    aws_iam as iam,
)
from slo_alarms_with_cdk.pipeline_stage import SloAlarmsPipelineStage

class SloAlarmsPipelineStack(Stack):
    
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # get github connection arn from parameter store
        connection_arn = ssm.StringParameter.from_string_parameter_name(
            self,
            "ConnectionARN",
            "slo-alarms-connection-arn"
            ).string_value

        # Pipeline code goes here
        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            synth=pipelines.ShellStep(
                "Synth",
                input=pipelines.CodePipelineSource.connection('yairst/slo-alarms-with-cdk', 'main',
                connection_arn=connection_arn
                ),
                commands=[
                    "npm install -g aws-cdk",  # Installs the cdk cli on Codebuild
                    "pip install -r requirements.txt",  # Instructs Codebuild to install required packages
                    "cdk synth",
                ]
            ),
        )

        deploy = SloAlarmsPipelineStage(self, "Deploy")
        deploy_stage = pipeline.add_stage(deploy)

        deploy_stage.add_post(
            pipelines.CodeBuildStep(
                "TagAlarmsWithSeverities",
                env={
                    "INFO_ARNS": deploy.alarms_arns_by_sev['INFO'],
                    "WARNING_ARN": deploy.alarms_arns_by_sev['WARNING'],
                    "MINOR_ARN": deploy.alarms_arns_by_sev['MINOR'],
                    "CRITICAL_ARN": deploy.alarms_arns_by_sev['CRITICAL'],
                },
                commands=[
                    "aws resourcegroupstaggingapi tag-resources \
                    --resource-arn-list $INFO_ARNS \
                    --tags Severity=INFO",
                    "aws resourcegroupstaggingapi tag-resources \
                    --resource-arn-list $WARNING_ARN \
                    --tags Severity=WARNING",
                    "aws resourcegroupstaggingapi tag-resources \
                    --resource-arn-list $MINOR_ARN \
                    --tags Severity=MINOR",
                    "aws resourcegroupstaggingapi tag-resources \
                    --resource-arn-list $CRITICAL_ARN \
                    --tags Severity=CRITICAL",
                ],
                role_policy_statements=[
                    iam.PolicyStatement(
                        actions=[
                            'tag:TagResources',
                            'cloudwatch:TagResource'
                        ],
                        resources=["*"]
                    )
                ]
            )
        )