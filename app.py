#!/usr/bin/env python3
import os

import aws_cdk as cdk

from slo_alarms_with_cdk.pipeline_stack import SloAlarmsPipelineStack
from slo_alarms_with_cdk.pipeline_stage import SloAlarmsPipelineStage


app = cdk.App()
SloAlarmsPipelineStack(app, "SloAlarmsPipelineStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.

    #env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */

    #env=cdk.Environment(account='123456789012', region='us-east-1'),

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    )

# add stage for quick test without triggering the pipeline, especially for changing
# values in config.yaml and test the resulting resources without messes up git history
# ref. to this solution: https://www.youtube.com/watch?v=v9lhX0tAgjY
# to use: uncomment the line below and run cdk deploy -a cdk.out/assembly-DeployWithoutPipeline/
# SloAlarmsPipelineStage(app, "DeployWithoutPipeline")
app.synth()
