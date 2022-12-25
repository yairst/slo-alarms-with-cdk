# Alerting on SLOs in AWS

A python-based application to proviosion stacks of SLO CloudWatch alarms on AWS services using AWS CDK.

## Background

In general, alerts rules defined on web or mobile services have low precision because of the tendency to define them with relatively low threshold (in purpose not to miss incidents) on short time-windows. These low precision alerts bring quickly to the so called "alert fatigue" phenomenon and eventually to ineffectiveness of the alerts.

In his post, [Alerting on SLOs like Pros](https://developers.soundcloud.com/blog/alerting-on-slos), Björn Rabenstein presents Google's ultimate solution to the above problem which is called *Multiwindow, Multi-Burn-Rate Alerts*. In order to well understand the concepts behind this solution, like SLOS, error budget and burn rates, you are encouraged to read this post and preferably Google's sources which is linked in it. Shortly, for each SLO, this solution sets several thresholds based on different error budget consumptions: 2 %, 5 %, and 10 %, on relatively long windows of 1,6 and 72 hours respectively. This setup leads to both high recall and high precision while keeping the detection time relatively short (since the evaluation period of the alert is 1 minute). To minimize the reset time, the solution defines short windows (1/12 of the long ones) such the alert fires only if both the long window and the short one cross over the threshold.

The following table summarize the multiwindow, multi-burn-rate setup for SLO period of 30 days:

|  Alert | Long Window | Short Window | Burn Rate Factor | Error Budget Consumed |
|:------:|:-----------:|:------------:|:----------------:|:---------------------:|
| Page   | 1h          | 5m           | 14.4             | 2%                    |
| Page   | 6h          | 30m          | 6                | 5%                    |
| Ticket | 3d          | 6h           | 1                | 10%                   |

## Project Structure and Architecture

### CloudWatch adapted setup

Since Cloudwatch alarms can't have period longer than 24 hours, I have made adjustment to the above table. In addition, I set the SLO duration to 28 days instead of 30 day as [recommended by Google](https://sre.google/workbook/implementing-slos/#:~:text=We%20recommend%20defining%20this%20period%20as%20an%20integral%20number%20of%20weeks%20so%20it%20always%20contains%20the%20same%20number%20of%20weekends). The resulted setup is:

|  Alarm   | Long Window | Short Window | Burn Rate Factor | Error Budget Consumed |
|:--------:|:-----------:|:------------:|:----------------:|:---------------------:|
| Critical | 30m         | 3m           | 13.44            | 1%                    |
| Minor    | 3h          | 15m          | 5.6              | 2.5%                  |
| Warning  | 1d          | 2h           | 1.12             | 4%                    |

Also note that I use different severities for each alarm. Each alarm is tagged with this severity using the [resourcegroupstaggingapi](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/resourcegroupstaggingapi/index.html) service of AWS CLI.

The multiwindow feature of the solution is implemented by defining [composite alarm](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Create_Composite_Alarm.html), for each burn-rate, that change state to ALARM only if both of the two underlying alarms, one for the long window and the other for the short one, goes into ALARM state.

Overall, for each SLO, a stack of 9 alarms is generated - 6 child alarms and 3 composite ones:

<img src="/res/cw-slo-alarms-architecture.drawio.svg"/>

### Configuration

There are 3 configuration files:
1. `burn_rates.yaml` - which configures the SLO period and the different windows and error budget consumption for each burn rate.
2. `metrics.yaml` - which configures the different metrics for each SLO type and AWS service. For now, the supported SLO types are error-rate and latency and the supported AWS services are ApiGateway and ApplicationELB.
3. `config.yaml` - In this file the user declare its SLO and the desired service and its dimensions on which the SLO alrms stack should be defined. For example, if we have an API named PetStore and our error rate SLO is 99.9 % than the `config.yaml` file will look like:

```yaml
[99.9]
namespace: 'AWS/ApiGateway'
dimensions_map: 
  ApiName: PetStore
```
## How to Use

1. Follow the instructions in [Working with the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/work-with.html). At the *Language-specific prerequisites* section in the above link choose [Python prerequisites](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html) and there follow the instructions only in the prerequisites section.

2. Fork this repo

3. Clone your forked repo:
    ```
    git clone git@github.com:<your_username>/slo-alarms-with-cdk.git
    ```
2. Create a Python virtual environment

    _On MacOS or Linux_
    ```
    $ python3 -m venv .venv
    ```

    _On Windows_
    ```
    $ python -m venv .venv
    ```

3. Activate virtual environment

    _On MacOS or Linux_
    ```
    $ source .venv/bin/activate
    ```

    _On Windows_
    ```
    % .venv\Scripts\activate.bat
    ```

    _On Windows, using Git Bash_ (as suggested [here](https://stackoverflow.com/questions/50902497/how-to-tell-if-virtualenv-is-activated-in-windows-git-bash))
    ```
    $ source .venv/Scripts/activate
    ```    

4. Install the required dependencies.

    ```
    $ pip install -r requirements.txt
    ```

5. If you are On windows replace `python3` with `python` in `cdk.json`.

5. Edit `config.yaml` with your desired values as detailed in the comments in the file. In particular, replace the values of the GitHub section with your forked repo ones, and specify your service, dimensions and SLO.

5. Synthesize (`cdk synth`) or deploy (`cdk deploy`) the example

    ```
    $ cdk deploy
    ```
6. If you want to fetch future changes from this repo, follow the steps [here](https://stackoverflow.com/questions/7244321/how-do-i-update-or-sync-a-forked-repository-on-github) or in [section 6 here](https://gist.github.com/0xjac/85097472043b697ab57ba1b1c7530274).

