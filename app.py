import aws_cdk as cdk
from slo_alarms_with_cdk.pipeline_stack import SloAlarmsPipelineStack
from slo_alarms_with_cdk.pipeline_stage import SloAlarmsPipelineStage
import yaml

### read configuration files ###

# burn rates and windows configuration
with open('burn_rates.yaml', mode='rb') as f:
    br_cfg = yaml.safe_load(f)

# metric configuration
with open('metrics.yaml', mode='rb') as f:
    metrics_cfg = yaml.safe_load(f)

# user's configuration: SLO and metric to alert on
with open('config.yaml', mode='rb') as f:
    cfg = yaml.safe_load(f)


app = cdk.App()
SloAlarmsPipelineStack(app, "SloAlarmsPipelineStack", br_cfg, metrics_cfg, cfg)

# add stage for quick test without triggering the pipeline, especially for changing
# values in config.yaml and test the resulting resources without messes up git history
# ref. to this solution: https://www.youtube.com/watch?v=v9lhX0tAgjY
# to use: uncomment the line below, run cdk synth and then cdk deploy -a cdk.out/assembly-DeployWithoutPipeline/ --all
# SloAlarmsPipelineStage(app, "DeployWithoutPipeline", br_cfg, metrics_cfg, cfg)
app.synth()
