from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
    aws_ssm as ssm,
    aws_sns as sns,
    aws_cloudwatch_actions as cw_actions,
    Duration
)
from constructs import Construct
import yaml
import json
import boto3
import time
import re
from .dynamic_burn_rate_stack import DynamicBurnRateStack

cw_client = boto3.client('cloudwatch')

class SloAlarmsWithCdkStack(Stack):

    @property
    def alarms_arns_by_sev(self):
        return self._alarms_arns_by_sev

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # read burn rates and windows configuration. DO NOT CHANGE!
        with open('burn_rates.yaml', mode='rb') as f:
            br_cfg = yaml.safe_load(f)
        self.slo_period = br_cfg['SLOperiod']

        # read user's configuration: SLO and metric to alert on
        with open('config.yaml', mode='rb') as f:
            cfg = yaml.safe_load(f)
        br_type = cfg['br_type']
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

        # get the SNS topic ARN for the action to be triggered by the composite alarms
        sns_topic_arn = ssm.StringParameter.from_string_parameter_name(
            self,
            "SnsTopicARN",
            "sns-topic-for-slo-alarms"
            ).string_value
        self.topic = sns.Topic.from_topic_arn(self, "SloAlarmsTopic", sns_topic_arn)

        # create constant part of the alarms arns
        account_id = Stack.of(self).account
        region = Stack.of(self).region
        self.arn_constant = ":".join(['arn:aws:cloudwatch', region, account_id, 'alarm'])

        # iterate on burn rates, severities and windows
        brs = ['high', 'mid', 'low']
        wins = ['LongWin', 'ShortWin']
        sevs = ['CRITICAL', 'MINOR', 'WARNING']
        self._alarms_arns_by_sev = {
            'INFO': '',
            'WARNING': self.arn_constant,
            'MINOR': self.arn_constant,
            'CRITICAL': self.arn_constant
        }
        self.composite_alarms = {}
        for br, sev in zip(brs, sevs):
            # calculate the burn rate and the corresponding threshold
            eb_frac = br_cfg[br]['ErrBudgetPer'] / 100
            self.alarm_win = br_cfg[br]['LongWin']
            br_val = 24 * 60 * self.slo_period / self.alarm_win * eb_frac
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
            self.alarm_id = "".join([self.namespace, self.SLOtype, 'SLO', br , 'BurnRate'])
            self.alarm_name = "-".join([self.namespace, self.SLOtype, 'SLO', br , 'burn-rate'])
            # avoid collision between alarm names in case of testing without pipeline
            if "DeployWithoutPipeline" in self.artifact_id:
                self.alarm_id = "Test" + self.alarm_id
                self.alarm_name = "test-" + self.alarm_name
            self._alarms_arns_by_sev[sev] += ':' + self.alarm_name  

            self.alarms = []
            for win in wins:
                # define math expression
                self.period = Duration.minutes(br_cfg[br][win])

                # assign child alarm id & name based on those of the composite alarm
                self.child_alarm_id = self.alarm_id + win
                self.child_alarm_name = "-".join([self.alarm_name, win])

                if alarm_type == 'metric':
                    alarm = self.create_metric_alarm()
                else:
                    alarm = self.create_math_expression_alarm()
                self.alarms.append(alarm)
                self._alarms_arns_by_sev['INFO'] += ":".join([self.arn_constant, self.child_alarm_name]) + " "
          
            # define composite alarm rule
            self.composite_alarms[br] = self.create_composite_alarm(br, SLO)

        if br_type == 'dynamic':
            # read Nslo metric from metrics.yaml, to be used in get_n_slo()
            self.n_slo_metric = metrics_cfg['Nslo'][self.namespace]

            # get number of requests for the last SLO period - Nslo
            n_slo = self.get_n_slo()

            # define required inputs for the dynamic burn-rate stack
            common_env_vars = {
                'NAMESPACE': self.namespace,
                'SLO_TYPE': self.SLOtype,
                'TEST': 'false',
                'REQUEST_COUNT_METRIC_NAME': self.n_slo_metric['metric_name'],
                'REQUEST_COUNT_STAT': self.n_slo_metric['statistic'],
            }
            if "DeployWithoutPipeline" in self.artifact_id:
                common_env_vars['TEST'] = 'true'

            update_thresh_env_vars = {
                'SLO': str(SLO[0]),
                'N_SLO': str(n_slo),
                'HIGH_BR_ERR_BUDGET_PER': str(br_cfg['high']['ErrBudgetPer']),
                'MID_BR_ERR_BUDGET_PER': str(br_cfg['mid']['ErrBudgetPer']),
                'LOW_BR_ERR_BUDGET_PER': str(br_cfg['low']['ErrBudgetPer']),
            }
            update_thresh_env_vars.update(common_env_vars)

            update_n_slo_env_vars = {
                'SLO_PERIOD': str(self.slo_period)
            }
            update_n_slo_env_vars.update(common_env_vars)

            sched_rates = {
                'High': br_cfg['high']['ShortWin'],
                'Mid': br_cfg['mid']['ShortWin'],
                'Low': br_cfg['low']['ShortWin']
            }

            DynamicBurnRateStack(
                self, "DynamicBurnRateStack",
                update_thresh_env_vars=update_thresh_env_vars,
                update_n_slo_env_vars=update_n_slo_env_vars,
                sched_rates=sched_rates
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
        alarm = math_expression.create_alarm(
            self, self.child_alarm_id,
            alarm_name=self.child_alarm_name,
            threshold=self.threshold,
            evaluation_periods=1
        )
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

    def generate_desc(self, br, SLO):
        if self.alarm_win < 60:
            time_unit = 'minutes'
            alarm_win = self.alarm_win
        else:
            alarm_win = self.alarm_win / 60
            if self.alarm_win == 60:
                time_unit = 'hour'
            else:
                time_unit = 'hours'

        if self.SLOtype == 'ErrorRate':
            desc = " ".join([
                'error rate in the last',
                str(alarm_win),
                time_unit,
                ', in', self.namespace, '-',
                json.dumps(self.dimensions_map)
            ])
            if br in ['high','mid']:
                suffix = '.'
                if br == 'high':
                    prefix = 'Very high '
                else:
                    prefix = 'High '
            else:
                prefix = 'The '
                suffix = ' is above normal.'
            desc = prefix + desc + suffix

        elif self.SLOtype == 'Latency':
            if self.namespace == 'AWS/ApiGateway':
                latency_time_unit = 'ms'
            else:
                latency_time_unit = 'seconds'
            thresh = round(100 - float(self.statistic[1:]), 2)
            if thresh >= 100:
                prefix = 'All of the requests in'
            else:
                prefix = " ".join([
                    'More than',
                    str(thresh),
                    '% of the requests in',
                ])
            desc = " ".join([
                prefix,
                self.namespace, '-',
                json.dumps(self.dimensions_map),
                'have latency above',
                str(SLO[1]),
                latency_time_unit,
                'in the last',
                str(alarm_win),
                time_unit, '.'
            ])

        return desc 

    def create_composite_alarm(self, br, SLO):
        alarm_rule = cw.AlarmRule.all_of(*self.alarms)
        desc = self.generate_desc(br, SLO)
        if (br == 'mid') or (br == 'low'):
            if (br == 'mid'):
                suppresor = self.composite_alarms['high']
            else: # br == 'low'
                aux_alarm_rule = cw.AlarmRule.any_of(
                    self.composite_alarms['high'],
                    self.composite_alarms['mid']
                )
                aux_alarm_id = "".join([
                    self.namespace, self.SLOtype,
                    'SLO', 'AuxiliaryMidOrHighSuppresorAlarm'
                ])
                aux_alarm_name = "-".join([
                    self.namespace, self.SLOtype,
                    'SLO', 'auxiliary-mid-or-high-suppresor-alarm'
                ])
                # avoid collision between alarm names in case of testing without pipeline
                if "DeployWithoutPipeline" in self.artifact_id:
                    aux_alarm_id = "Test" + aux_alarm_id
                    aux_alarm_name = "test" + aux_alarm_name
                self._alarms_arns_by_sev['INFO'] += ":".join([
                    self.arn_constant, aux_alarm_name]) + " "
                suppresor = cw.CompositeAlarm(
                    self, aux_alarm_id,
                    alarm_rule=aux_alarm_rule,
                    composite_alarm_name=aux_alarm_name,
                )
            composite_alarm = cw.CompositeAlarm(
                self, self.alarm_id,
                alarm_rule=alarm_rule,
                composite_alarm_name=self.alarm_name,
                alarm_description=desc,
                actions_suppressor=suppresor
            )
        else: # br == 'high'
            composite_alarm = cw.CompositeAlarm(
                self, self.alarm_id,
                alarm_rule=alarm_rule,
                composite_alarm_name=self.alarm_name,
                alarm_description=desc
            )
        
        composite_alarm.add_alarm_action(cw_actions.SnsAction(self.topic))
        return composite_alarm

    def get_n_slo(self):
        time_end = int(time.time())
        time_start = time_end - 3600 * 24 * self.slo_period
        req_count = cw_client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "n_slo",
                "MetricStat": {
    			    "Metric": {
    				    "Namespace": self.namespace,
    				    "MetricName": self.n_slo_metric['metric_name'],
    				    "Dimensions": self.dimensions_dict_to_list()
    			    },
    			    "Period": 3600 * 24,
    			    "Stat": self.n_slo_metric['statistic']
    		    },
    		    "ReturnData": True,
    	    },
    	],
        StartTime=time_start,
        EndTime=time_end
	    )
        n_slo = int(sum(req_count['MetricDataResults'][0]['Values']))
        return n_slo

    def dimensions_dict_to_list(self):
        dim_l = []
        for k, v in self.dimensions_map.items():
            cur = {"Name": k, "Value": v}
            dim_l.append(cur)
        return dim_l
