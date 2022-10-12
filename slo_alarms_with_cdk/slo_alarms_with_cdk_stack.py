from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
    Duration
)
from constructs import Construct
import configparser

SLO = 99.9

class SloAlarmsWithCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        br_cfg = configparser.ConfigParser()
        br_cfg.read('burn_rates.ini')

        brs = ['high', 'mid', 'low']
        wins = ['LongWin', 'ShortWin']

        for br in brs:
            # calculate the burn rate and the corresponding threshold
            slo_period = float(br_cfg['SLO']['Period'])
            eb_frac = float(br_cfg[br]['ErrBudgetPer']) / 100
            alarm_win = float(br_cfg[br]['LongWin'])
            br_val = 24 * 60 * slo_period / alarm_win * eb_frac
            threshold = br_val * (1 - SLO / 100)

            alarm_id = "".join(['ErrorRateSLO', br , 'BurnRate'])
            alarm_name = "-".join(['error-rate-SLO', br , 'burn-rate'])  

            alarms = []
            for win in wins:
                # define metric for the given window
                metric = cw.Metric(
                    namespace='AWS/ApiGateway',
                    metric_name='5XXError',
                    dimensions_map={'ApiName': 'PetStore'},
                    period=Duration.minutes(int(br_cfg[br][win])),
                )

                # define alarm on the above metric where the threshold is based on
                # the SLO and the calculated burn_rate
                child_alarm_id = alarm_id + win
                child_alarm_name = "-".join([alarm_name, win])
              
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
