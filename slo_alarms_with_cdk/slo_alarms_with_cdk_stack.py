from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
    aws_ssm as ssm,
    Duration
)
from constructs import Construct
import yaml


class SloAlarmsWithCdkStack(Stack):

    @property
    def alarms_arns_by_sev(self):
        return self._alarms_arns_by_sev

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
        self.namespace = cfg['namespace']
        self.dimensions_map = cfg['dimensions_map']
        if len(SLO) == 2:
            self.SLOtype = 'Latency'
        else:
            self.SLOtype = 'ErrorRate'

        # read metric configuration
        with open('metrics.yaml', mode='rb') as f:
            metrics_cfg = yaml.safe_load(f)
        if 'metric_name' in metrics_cfg[self.SLOtype][self.namespace].keys():
            alarm_type = 'metric'
            self.metric_name = metrics_cfg[self.SLOtype][self.namespace]['metric_name']
        else:
            alarm_type = 'math'
            self.math_expression = metrics_cfg[self.SLOtype][self.namespace]['math_expression']
            self.using_metrics = metrics_cfg[self.SLOtype][self.namespace]['using_metrics']
        if self.SLOtype == 'ErrorRate':
            self.statistic = metrics_cfg[self.SLOtype][self.namespace]['statistic']
            if alarm_type == 'math':
                self.metrics_dict = self.get_metrics_for_math_expresssion()

        # create constant part of the alarms arns
        account_id = Stack.of(self).account
        region = Stack.of(self).region
        arn_constant = ":".join(['arn:aws:cloudwatch', region, account_id, 'alarm'])

        # iterate on burn rates, severities and windows
        brs = ['high', 'mid', 'low']
        wins = ['LongWin', 'ShortWin']
        sevs = ['CRITICAL', 'MINOR', 'WARNING']
        self._alarms_arns_by_sev = {
            'INFO': '',
            'WARNING': arn_constant,
            'MINOR': arn_constant,
            'CRITICAL': arn_constant
        }
        for br, sev in zip(brs, sevs):
            # calculate the burn rate and the corresponding threshold
            eb_frac = br_cfg[br]['ErrBudgetPer'] / 100
            alarm_win = br_cfg[br]['LongWin']
            br_val = 24 * 60 * slo_period / alarm_win * eb_frac
            self.threshold = round(br_val * (1 - SLO[0] / 100), 5)
            if self.SLOtype == 'Latency':
                # in latency case there is a possibility to get threshold above 1
                # in case of relatively low SLO percentage and high burn rate.
                # In this case we set the percentile of the metric to zero
                # meaning that only if all the requests are above the latency threshold
                # the alarm should be fired.
                per = max([0, 100 * (1 - self.threshold)])
                self.statistic = 'p' + "{:05.2f}".format(per)
                self.threshold = SLO[1]
                if alarm_type == 'math':
                    self.metrics_dict = self.get_metrics_for_math_expresssion()

            # prepare the id and the name for the composite alarm. to be used
            # for the child alarms
            alarm_id = "".join([self.namespace, self.SLOtype, 'SLO', br , 'BurnRate'])
            alarm_name = "-".join([self.namespace, self.SLOtype, 'SLO', br , 'burn-rate'])
            self._alarms_arns_by_sev[sev] += ':' + alarm_name  

            alarms = []
            for win in wins:
                # define math expression
                self.period = Duration.minutes(br_cfg[br][win])

                # assign child alarm id & name based on those of the composite alarm
                self.child_alarm_id = alarm_id + win
                self.child_alarm_name = "-".join([alarm_name, win])

                if alarm_type == 'metric':
                    alarm = self.create_metric_alarm()
                else:
                    alarm = self.create_math_expression_alarm()
                alarms.append(alarm)
                self._alarms_arns_by_sev['INFO'] += ":".join([arn_constant, self.child_alarm_name]) + " "
          
            # define composite alarm rule
            alarm_rule = cw.AlarmRule.all_of(*alarms)
            cw.CompositeAlarm(
                self, alarm_id,
                alarm_rule=alarm_rule,
                composite_alarm_name=alarm_name
            )


    def get_metrics_for_math_expresssion(self):
        metrics_dict = {}
        for metric_id, metric_name in self.using_metrics.items():
            metric = cw.Metric(
                namespace=self.namespace,
                metric_name=metric_name,
                dimensions_map=self.dimensions_map,
                statistic=self.statistic,
            )
            metrics_dict[metric_id] = metric
        return metrics_dict

    def create_math_expression_alarm(self):
        math_expression = cw.MathExpression(
            expression=self.math_expression,
            using_metrics=self.metrics_dict,
            period=self.period,
            label=self.SLOtype
        )
        alarm = math_expression.create_alarm(self,
                                            self.child_alarm_id,
                                            alarm_name=self.child_alarm_name,
                                            threshold=self.threshold,
                                            evaluation_periods=1)
        return alarm

    def create_metric_alarm(self):
        # define metric for the given window
        metric = cw.Metric(
            namespace=self.namespace,
            metric_name=self.metric_name,
            dimensions_map=self.dimensions_map,
            period=self.period,
            statistic=self.statistic
        )
        alarm = cw.Alarm(
            self, self.child_alarm_id,
            metric=metric,
            threshold=self.threshold,
            alarm_name=self.child_alarm_name,
            evaluation_periods=1,
        )
        return alarm
