import boto3
import datetime
import os
import json
from utils import get_slo_namesape_and_sli_name

cw_client = boto3.client('cloudwatch')

# get start and end time for GetMetricData:
time_end = datetime.datetime.now()
time_end = time_end.replace(minute=0, second=0, microsecond=0)
SLOperiod = int(os.environ['SLO_PERIOD'])
time_start = time_end - datetime.timedelta(days=SLOperiod)

def lambda_handler(event, context):

    # retrive env vars
    namespace = os.environ['NAMESPACE']
    SLOtype = os.environ['SLO_TYPE']
    slo = json.loads(os.environ['SLO'])
    test = os.environ['TEST'] == 'true'
    
    #read alarm to exract metric or math expression for get_metric
    alarm_name = "-".join([namespace, SLOtype, 'SLO-low-burn-rate-LongWin'])
    if test:
        alarm_name = 'test-' + alarm_name
    alarm = cw_client.describe_alarms(AlarmNames=[alarm_name])['MetricAlarms'][0]

    # get metric_queries from alarm and set it to the SLO period
    slo_period_seconds = SLOperiod * 24 * 3600
    if 'MetricName' in alarm.keys(): # single metric alarm
        metric_queries = single_metric_to_metric_data_queries(alarm, slo_period_seconds)
    else: # math expression
        metric_queries = alarm['Metrics']
        for i, _ in enumerate(metric_queries):
            if 'MetricStat' in metric_queries[i].keys():
                metric_queries[i]['MetricStat']['Period'] = slo_period_seconds

    if SLOtype == 'ErrorRate': 
    # get the SLI for the SLOperiod
        res = cw_client.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=time_start, EndTime=time_end
        )
        sli = res['MetricDataResults'][0]['Values'][-1] * 100
        # 'Values' should contain only one element since period == end_time - start_time.
        # however, just for case that somehow it will include 2 datapoints we need to take
        # the last one, since the datapoints are ordered from recent timestamps to the earliest one
        # and always the earliest datapoints will be with the whole period and the latest one
        # can be only on part of the period. 
    else: # latency: need to find the sli by binary search
        sli = get_latecny_sli(metric_queries, slo)

    # publish the calculated metric/ percentile as custom metric
    slo_namespace, sli_name = get_slo_namesape_and_sli_name(namespace, SLOtype, slo, test=test)
    for i, _ in enumerate(metric_queries):
        if 'MetricStat' in metric_queries[i].keys():
            dimensions = metric_queries[i]['MetricStat']['Metric']['Dimensions']
            break
    cw_client.put_metric_data(
        Namespace=slo_namespace,
        MetricData=[
            {
                'MetricName': sli_name,
                'Dimensions': dimensions,
                'Timestamp': time_end,
                'Value': round(sli, 2),
                'Unit': 'Percent'
            },
        ]
    )


def single_metric_to_metric_data_queries(alarm, period):
    if 'Statistic' in alarm.keys():
        stat = alarm['Statistic']
    else:
        stat = alarm['ExtendedStatistic']
    metric_query = {
        "Id": "sli",
        "MetricStat": {
            "Metric": {
                "Namespace": alarm['Namespace'],
                "MetricName": alarm['MetricName'],
                "Dimensions": alarm['Dimensions']
            },
            "Period": period,
            "Stat": stat
        },
        "ReturnData": True,
    }
    return [metric_query]

def get_latecny_sli(metric_queries, slo, max_n_iters = 20):

    slo_latency = slo[1]
    perc_high = 100
    perc = slo[0]
    perc_low = 0
    delta = 1000

    for i in range(max_n_iters):
        perc_str = 'p' + "{:05.2f}".format(perc)

        # most (if not all) of the cases will be single metric. just in case
        # that the latency sli is somehow based on math expression, the following loop is
        # needed. Of course it catches also single metric case
        for i, _ in enumerate(metric_queries):
            if 'MetricStat' in metric_queries[i].keys():
                metric_queries[i]['MetricStat']['Stat'] = perc_str

        # get latency for current perc
        res = cw_client.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=time_start, EndTime=time_end
        )

        latency = res['MetricDataResults'][0]['Values'][-1]
        
        delta = latency - slo_latency
        
        if abs(delta) < 0.01 * slo_latency:
            break
        elif delta > 0:
            perc_high = perc
            perc = (perc + perc_low) / 2
        else:
            perc_low = perc
            perc = (perc + perc_high) / 2
    
    return perc
