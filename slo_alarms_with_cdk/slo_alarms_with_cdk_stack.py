from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
    Duration
)
from constructs import Construct
import yaml


class SloAlarmsWithCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # read burn rates and windows configuration. DO NOT CHANGE!
        with open('burn_rates.yaml', mode='rb') as f:
            br_cfg = yaml.safe_load(f)
        slo_period = br_cfg['SLOperiod']

        # read user's configuration: SLO and metric to alert on
        with open('config.yaml', mode='rb') as f:
            cfg = yaml.safe_load(f)
        SLO = cfg['SLO']
        namespace = cfg['namespace']
        metric_name = cfg['metric_name']
        dimensions_map = cfg['dimensions_map']
        if isinstance(cfg['SLO'], list):
            SLOtype = 'Latency'
        else:
            SLOtype = 'ErrorRate'

        # iterate on burn rates and windows
        brs = ['high', 'mid', 'low']
        wins = ['LongWin', 'ShortWin']
        for br in brs:
            # calculate the burn rate and the corresponding threshold
            eb_frac = br_cfg[br]['ErrBudgetPer'] / 100
            alarm_win = br_cfg[br]['LongWin']
            br_val = 24 * 60 * slo_period / alarm_win * eb_frac
            threshold = br_val * (1 - SLO / 100)

            # prepare the id and the name for the composite alarm. to be used
            # for the child alarms
            alarm_id = "".join([SLOtype, 'SLO', br , 'BurnRate'])
            alarm_name = "-".join([SLOtype, 'SLO', br , 'burn-rate'])  

            alarms = []
            for win in wins:
                # define metric for the given window
                metric = cw.Metric(
                    namespace=namespace,
                    metric_name=metric_name,
                    dimensions_map=dimensions_map,
                    period=Duration.minutes(br_cfg[br][win]),
                )

                # assign child alarm id & name based on those of the composite alarm
                child_alarm_id = alarm_id + win
                child_alarm_name = "-".join([alarm_name, win])

                # define alarm on the above metric where the threshold is based on
                # the SLO and the calculated burn_rate              
                alarm = cw.Alarm(
                    self, child_alarm_id,
                    metric=metric,
                    threshold=threshold,
                    alarm_name=child_alarm_name,
                    evaluation_periods=1
                )
                alarms.append(alarm)
            
            # define composite alarm rule
            alarm_rule = cw.AlarmRule.all_of(*alarms)
            cw.CompositeAlarm(
                self, alarm_id,
                alarm_rule=alarm_rule,
                composite_alarm_name=alarm_name
            )
