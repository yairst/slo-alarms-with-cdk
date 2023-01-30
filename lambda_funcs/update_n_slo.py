import boto3
import os
import time

lambda_client = boto3.client('lambda')
cw_client = boto3.client('cloudwatch')

def lambda_handler(event, context):

    # retrive required env_vars and dimensions
    namespace = os.environ['NAMESPACE']
    SLOtype = os.environ['SLO_TYPE'] 
    alarm_name_prefix = "-".join([namespace, SLOtype, 'SLO', 'high'])
    if os.environ['TEST'] == 'true':
        alarm_name_prefix = 'test-' + alarm_name_prefix
    alarms = cw_client.describe_alarms(AlarmNamePrefix=alarm_name_prefix)
    alarm = alarms['MetricAlarms'][0]
    if 'MetricName' in alarm.keys(): # single metric alarm
        dims = alarm['Dimensions']
    else: # math expression alarm
        dims = alarm['Metrics'][0]['MetricStat']['Metric']['Dimensions']

    # get start and end time for GetMetricData:
    time_end = int(time.time())
    time_start = time_end - 3600 * 24 * int(os.environ['SLO_PERIOD'])

    # get current n_slo
    req_count = cw_client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "reqCount",
                "MetricStat": {
    			    "Metric": {
    				    "Namespace": namespace,
    				    "MetricName": os.environ['REQUEST_COUNT_METRIC_NAME'],
    				    "Dimensions": dims
    			    },
    			    "Period": 3600 * 24,
    			    "Stat": os.environ['REQUEST_COUNT_STAT']
    		    },
    		    "ReturnData": True,
    	    },
    	],
        StartTime=time_start,
        EndTime=time_end
	)

    n_slo = int(sum(req_count['MetricDataResults'][0]['Values']))

    # get current env vars along with current n_slo
    func_config = lambda_client.get_function_configuration(
        FunctionName=os.environ['UPDATE_THRESH_FUNC'],
    )
    env_vars = func_config['Environment']['Variables']
    print(f"current n_slo: {env_vars['N_SLO']}")

    # update n_slo
    env_vars['N_SLO'] = str(n_slo)
    print(f"new n_slo: {env_vars['N_SLO']}")

    response= lambda_client.update_function_configuration(
        FunctionName=os.environ['UPDATE_THRESH_FUNC'],
        Environment={
            'Variables': env_vars
        }
    )

    print(response)