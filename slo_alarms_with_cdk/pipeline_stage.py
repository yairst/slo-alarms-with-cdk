from constructs import Construct
from aws_cdk import (
    Stage
)

from .slo_alarms_with_cdk_stack import SloAlarmsWithCdkStack
from .dashboard_stack import SloDashboardStack

class SloAlarmsPipelineStage(Stage):

    @property
    def alarms_arns_by_sev(self):
        return self._alarms_arns_by_sev

    def __init__(
            self, scope: Construct, id: str, br_cfg: dict, metrics_cfg: dict,
            cfg: dict, **kwargs
        ) -> None:
        super().__init__(scope, id, **kwargs)

        alarms_stack = SloAlarmsWithCdkStack(
            self, "SloAlarmsStack", br_cfg, metrics_cfg, cfg
        )
        self._alarms_arns_by_sev = alarms_stack.alarms_arns_by_sev

        comp_alarms = list(alarms_stack.composite_alarms.values())
        dashboard_stack = SloDashboardStack(
            self, "SloDashboardStack", br_cfg, cfg, comp_alarms
        )