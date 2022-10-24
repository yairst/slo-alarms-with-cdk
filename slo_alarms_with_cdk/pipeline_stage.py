from constructs import Construct
from aws_cdk import (
    Stage
)

from .slo_alarms_with_cdk_stack import SloAlarmsWithCdkStack

class SloAlarmsPipelineStage(Stage):

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        service = SloAlarmsWithCdkStack(self, "SloAlarmsStack")