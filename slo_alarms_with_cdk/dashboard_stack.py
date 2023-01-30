from aws_cdk import (
    Stack,
    Duration,
    aws_cloudwatch as cw,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets
)
from constructs import Construct
from lambda_funcs.utils import get_slo_namesape_and_sli_name

class SloDashboardStack(Stack):

    def __init__(
            self, scope: Construct, construct_id: str, br_cfg: dict,
            cfg: dict, comp_alarms: list, **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # initialize
        self.SLOperiod = br_cfg['SLOperiod']
        self.SLOtype = cfg['SLOtype']
        self.slo = cfg['SLO']
        self.namespace = cfg['namespace']
        self.dimensions = cfg['dimensions_map']
        self.sli_publish_rate = Duration.hours(6)
        self.test = "DeployWithoutPipeline" in self.artifact_id
        self.slo_namespace, self.sli_name = get_slo_namesape_and_sli_name(
            self.namespace, self.SLOtype, self.slo, test=self.test
        )
        self.sli_metric = cw.Metric(
            metric_name=self.sli_name, namespace=self.slo_namespace,
            dimensions_map=self.dimensions, period=self.sli_publish_rate,
            statistic=cw.Stats.AVERAGE
        )
        self.comp_alarms = comp_alarms

        # dashboard
        dash_name = 'slos-status'
        if self.test:
            dash_name = 'test-' + dash_name
        dashboard = cw.Dashboard(
            self, "SloDashboard", dashboard_name=dash_name,
            start=f'-P{self.SLOperiod}D'
        )

        # lambda function to publish sli
        lambda_role_policy_statements = [
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricData",
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:PutMetricData",
                ],
                resources=["*"],
            )
        ] 

        lambda_name = 'publish-slis'
        if self.test:
            lambda_name = 'test-' + lambda_name

        env_vars = {
            'SLO_PERIOD': str(self.SLOperiod),
            'NAMESPACE': self.namespace,
            'SLO_TYPE': self.SLOtype,
            'SLO': str(self.slo),
            'TEST': 'false'
        }
        if self.test:
            env_vars['TEST'] = 'true'

        publish_sli = _lambda.Function(
            self, 'PublishSLIs',
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler='publish_sli.lambda_handler',
            code=_lambda.Code.from_asset('lambda_funcs'),
            environment=env_vars,
            initial_policy=lambda_role_policy_statements,
            function_name=lambda_name
        )

        rule_name="OnceEvery6HourScheduler"
        if self.test:
            rule_name = 'test-' + rule_name
        scheduler = events.Rule(
            self, "OnceEvery6HourScheduler",
            schedule=events.Schedule.rate(self.sli_publish_rate),
            rule_name=rule_name
        )
        scheduler.add_target(targets.LambdaFunction(publish_sli))

        ### first line: SLO, SLI, error budget and alarms status ###

        # preliminaries
        if self.SLOtype == 'ErrorRate':
            slo_str = str(self.slo[0]) + ' %'
        else:
            slo_str = str(self.slo[0]) + ' %, ' + str(self.slo[1]) + ' ms'
        eb_metrics = self.get_error_budget_metrics()

        dashboard.add_widgets(
            # SLO widget 
            cw.TextWidget(
                markdown="".join([
                    "# SLO\n",
                    "## ", self.SLOtype, "\n",
                    "## ", slo_str, "\n",
                    "## ", str(self.SLOperiod), " Days"
                ]),
                height=5, width=4
            ),
            # SLI widget
            cw.SingleValueWidget(
                title=f'SLI, {self.SLOperiod}-days-rolling-window',
                metrics=[self.sli_metric], full_precision=True,
                height=5, width=6
            ),
            # Error Budget Widget
            cw.GraphWidget(
                left=eb_metrics, left_y_axis=cw.YAxisProps(label='%', show_units=False),
                title=f'Error Budget, {self.SLOperiod}-days-rolling-window',
                stacked=True, period=self.sli_publish_rate, statistic=cw.Stats.AVERAGE,
                height=5, width=6
            ),
            # Alarms Status Widget
            cw.AlarmStatusWidget(
                alarms=comp_alarms, height=5,
                sort_by=cw.AlarmStatusWidgetSortBy.STATE_UPDATED_TIMESTAMP
            )
        )
    
    def dim_dict_to_list(self):
        l = []
        for key, value in self.dimensions.iteritems():
            temp = [key,value]
            l.append(temp)
        return l

    def get_error_budget_metrics(self):
        eb = cw.MathExpression(
            expression = f'(sli - {self.slo[0]})/(100 - {self.slo[0]})*100',
            using_metrics={'sli': self.sli_metric}
        )
        eb_non_neg = cw.MathExpression(
            expression="IF(eb >= 0, eb, 0)",
            using_metrics={'eb': eb},
            color=cw.Color.GREEN,
            label='Error Budget >= 0 %'
        )
        eb_neg = cw.MathExpression(
            expression="IF(eb < 0, eb, 0)",
            using_metrics={'eb': eb},
            color=cw.Color.RED,
            label='Error Budget < 0 %'
        )
        return [eb_non_neg, eb_neg]

