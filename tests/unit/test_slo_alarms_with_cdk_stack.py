import aws_cdk as core
import aws_cdk.assertions as assertions

from slo_alarms_with_cdk.slo_alarms_with_cdk_stack import SloAlarmsWithCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in slo_alarms_with_cdk/slo_alarms_with_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = SloAlarmsWithCdkStack(app, "slo-alarms-with-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
