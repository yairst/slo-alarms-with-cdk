from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
    Duration
)
from constructs import Construct

class SloAlarmsWithCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        metric = cw.Metric(
            namespace='AWS/ApiGateway',
            metric_name='5XXError',
            dimensions_map={'ApiName': 'PetStore'},
            period=Duration.minutes(30),
        )       
    
        cw.Alarm(
            self, 'myFirstCDKAlarm',
            metric=metric,
            threshold=0.33,
            alarm_name='yair-pets-error-rate-by-cdk',
            evaluation_periods=1
        )
