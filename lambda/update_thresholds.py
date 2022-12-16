import boto3
import time
import os

cw_client = boto3.client('cloudwatch')
ssm_client = boto3.client('ssm')

def lambda_handler(event, context):

    # retrive env vars and deduce the relevant alarms from the scheduled event
    namespace = os.environ['NAMESPACE']
    SLOtype = os.environ['SLO_TYPE']
    alarm_name_prefix = "-".join([namespace, SLOtype, 'SLO'])
    if 'High' in event['resources'][0]:
        alarm_name_prefix += "-" + 'high'
        eb_per_thresh = float(os.environ['HIGH_BR_ERR_BUDGET_PER']) 
    elif 'Mid' in event['resources'][0]:
        alarm_name_prefix += "-" + 'mid'
        eb_per_thresh = float(os.environ['MID_BR_ERR_BUDGET_PER'])
    else:
        alarm_name_prefix += "-" + 'low'
        eb_per_thresh = float(os.environ['LOW_BR_ERR_BUDGET_PER'])

    if os.environ['TEST'] == 'true':
        alarm_name_prefix = 'test-' + alarm_name_prefix
    alarms = cw_client.describe_alarms(AlarmNamePrefix=alarm_name_prefix)
    # should return one composite alarms and 2 metric alarms. we need only the metric ones:
    alarms = alarms['MetricAlarms']

    # extract the periods and dimensions of the alarms. to do it we need to
    # check if they are single metric alarms or based on math expression - 
    # can be done by check if MetricName field exists: if yes they are single metric alarm.
    for alarm in alarms:
        if 'MetricName' in alarm.keys(): # single metric alarm
            if 'Long' in alarm['AlarmName']:
                long_win = alarm['Period']
                dims = alarm['Dimensions']
            else:
                short_win = alarm['Period']
        else: # math expression alarm
            if 'Long' in alarm['AlarmName']:
                long_win = alarm['Metrics'][0]['Period']
                dims = alarm['Metrics'][0]['MetricStat']['Metric']['Dimensions']
            else:
                short_win = alarm['Metrics'][0]['Period']
    
    # get start and end time for GetMetricData:
    time_end = int(time.time())
    time_start = time_end - long_win

    # get total request count for the alarm window
    req_count = cw_client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "req_count",
                "MetricStat": {
    			    "Metric": {
    				    "Namespace": os.environ['NAMESPACE'],
    				    "MetricName": os.environ['REQUEST_COUNT_METRIC_NAME'],
    				    "Dimensions": dims
    			    },
    			    "Period": short_win,
    			    "Stat": os.environ['REQUEST_COUNT_STAT']
    		    },
    		    "ReturnData": True,
    	    },
    	],
        StartTime=time_start,
        EndTime=time_end
	)

    ### calculate the new threshold and update the alarms ###

    # calculate number of requests in the alarm window, n_a
    n_a = max(1, sum(req_count['MetricDataResults'][0]['Values'])) # to prevent division by zero in case n_a = 0
    # assuming that n_slo is very large, n_a = 1 will result in desired threshold >> 1

    # get n_slo and slo
    n_slo = float(os.environ['N_SLO'])
    slo = float(os.environ['SLO'])

    # keys need to be removed before return the described alarms json to put_metric_alarm:
    keys_to_exclude = [
    'AlarmArn', 'AlarmConfigurationUpdatedTimestamp',
    'StateValue', 'StateReason', 'StateReasonData', 'StateUpdatedTimestamp',
    ]

    for alarm in alarms:
        for k in keys_to_exclude:
            alarm.pop(k)
        new_thresh = n_slo / n_a * (eb_per_thresh / 100) * (1 - slo / 100)
        if SLOtype == 'ErrorRate':
            if alarm['Threshold'] != new_thresh:
                alarm['Threshold'] = new_thresh
                cw_client.put_metric_alarm(**alarm)        
        else: # latency
            percentile = max([0, 100 * (1 - new_thresh)])
            new_statistic = 'p' + "{:05.2f}".format(percentile)
            if 'MetricName' in alarm.keys(): # single metric alarm
                if alarm['ExtendedStatistic'] != new_statistic:
                    alarm['ExtendedStatistic'] = new_statistic
                    cw_client.put_metric_alarm(**alarm)
            else: # math expression alarm
                if alarm['Metrics'][0]['MetricStat']['Stat'] != new_statistic:
                    for i in len(alarm['Metrics']):
                        alarm['Metrics'][i]['MetricStat']['Stat'] = new_statistic
                    cw_client.put_metric_alarm(**alarm)
