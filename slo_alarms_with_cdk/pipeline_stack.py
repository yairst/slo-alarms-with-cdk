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
        
        # define the alarms provision stage
        deploy = SloAlarmsPipelineStage(self, "Deploy")

        # define a sequence of post stages for tagging the alarms with severities.
        # Need to define each severity as different step, since defining all the tagging
        # in one step, with four different commands for each severity, results in "Rate exceeded"
        # error message for 3 of the four api calls.
        sevs = ['CRITICAL', 'MINOR', 'WARNING', 'INFO']
        steps_seq = []
        for sev in sevs:
            step = pipelines.CodeBuildStep(
                "".join(["Tag", sev, "Alarms"]),
                commands = [
                    "".join([
                        "aws resourcegroupstaggingapi tag-resources --resource-arn-list ",
                        deploy.alarms_arns_by_sev[sev], " ",
                        "--tags Severity=", sev
                    ])
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
            steps_seq.append(step)
        steps_seq = pipelines.CodeBuildStep.sequence(steps_seq)

        # add the stages to the pipeline
        pipeline.add_stage(deploy, post=steps_seq)