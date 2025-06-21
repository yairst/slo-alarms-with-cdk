# Alerting on SLOs in AWS

A python-based application for deploying  stacks of SLO CloudWatch alarms on AWS services using AWS CDK.

## Background

In general, alerts rules defined on web or mobile applications have low precision because of the tendency to define them with relatively low threshold (in purpose not to miss incidents) on short time-windows. These low precision alerts bring quickly to the so called "alert fatigue" phenomenon and eventually to ineffectiveness of the alerts.

In his post, [Alerting on SLOs like Pros](https://developers.soundcloud.com/blog/alerting-on-slos), Björn Rabenstein presents Google's ultimate solution to the above problem which is called *Multiwindow, Multi-Burn-Rate Alerts*. In order to well understand the concepts behind this solution, like SLIs, SLOS, error budget and burn rates, you are encouraged to read this post and preferably Google's sources which are linked in it. To summarize, the definitions of the above terms are:
 - **SLI** - Service Level Indicator: A metric that describes some aspect of the reliability of a service. Defined as the ratio between the number of "good" events to the total number of events. For example, the ratio between the number of all the requests which hasn't been responded with 5xx http-code to the total number of requests. 
 - **SLO** - Service Level Objective. A threshold on a corresponding Service Level Indicator (SLI) aligned with the reliability goal for that SLI. For example, 99.9 % of the events should be non-5xx events.
 - **Error Budget** - The allowed number of "bad" events for pre-defined SLO period. For example, if the SLO is 99.9 % and there are one million requests in the SLO period (say, 28 days), then the error budget is 1,000.
 - **Burn Rate** - The rate in which the error budget is consumed, relative to the SLO. For example, if the SLO is 99.9 %, which defined an average 0.1 % error rate for the SLO period, and at the moment (for the last x minutes), the error rate is 0.3 %, than the burn rate is 3.

One of the key insights underlying Google's solution is that any single-threshold alarm will inevitably lead to low recall or low precision. Hence, their solution is based on multiple thresholds or burn rates. In detail, for a given SLO, the solution sets several thresholds based on different error budget consumptions: 2 %, 5 %, and 10 %, on relatively long windows of 1,6 and 72 hours respectively. This setup leads to both high recall and high precision while keeping the detection time relatively short (since the evaluation period of the alert is 1 minute). To minimize the reset time, the solution defines short windows (1/12 of the long ones) such the alert fires only if both the long window and the short one cross over the threshold.

### Static Burn Rate

The following table summarize the multiwindow, multi-burn-rate setup for SLO period of 30 days:

|  Alert | Long Window | Short Window | Burn Rate Factor | Error Budget Consumed |
|:------:|:-----------:|:------------:|:----------------:|:---------------------:|
| Page   | 1h          | 5m           | 14.4             | 2%                    |
| Page   | 6h          | 30m          | 6                | 5%                    |
| Ticket | 3d          | 6h           | 1                | 10%                   |

It is important to note, that the starting point for each alert is the error budget consumption and its corresponding long window. The chosen values are the ones that [recommended by google as starting numbers](https://sre.google/workbook/alerting-on-slos/#:~:text=We%20recommend%202%25%20budget%20consumption%20in%20one%20hour%20and%205%25%20budget%20consumption%20in%20six%20hours%20as%20reasonable%20starting%20numbers%20for%20paging%2C%20and%2010%25%20budget%20consumption%20in%20three%20days%20as%20a%20good%20baseline%20for%20ticket%20alerts). After set these values, it is possible to calculate the burn rates using the following formula:

$$ BurnRate = {SloPeriod \over LongWindow} \times PercentageOfErrorBudgetConsumprion $$

For example, the calculation of the 14.4 burn rate is:

$$ {{30 \times 24} \over 1} \times 2 \\% = 14.4 $$

and then the threshold will be:

$$ Threshold = BurnRate \times (1 - SLO) $$

For example, for 99.9 % SLO the threshold of the 1-hour alert will be: $14.4 \times 0.1\\% = 1.44\\%$

### Dynamic Burn Rates

Google's solution constitutes a significant milestone in the ability to create alerting setup with both high recall and high precision. However, as I show in my [two-part post](https://medium.com/@yairstark/error-budget-is-all-you-need-part-2-ad41891e1132), their setup is not suitable to varying-traffic services (night vs day, business days vs weekends, etc.). In this post I prove mathematically that Google's static burn rate holds only in the case of constant traffic and I show that the correct expression for the burn rate should be dynamic, as follows:

$$ BurnRate (t) = {N_{slo}(t) \over N_a(t)} \times EBP $$

Where $N_{slo}(t)$ is the total number of events in the SLO period, $N_a(t)$ is the total number of events in the alarm's window and EBP is the percentage of error budget consumption that we want to alarm on. Note that the dynamic burn-rate expression generalizes Google's one and they are equal only when the number of events in the alarm's window is equal to the average number of events in this window.


## Project Structure and Architecture

### CloudWatch adapted setup

Since Cloudwatch alarms can't have period longer than 24 hours, I have made adjustment to the above table. In addition, I set the SLO duration to 28 days instead of 30 day as [recommended by Google](https://sre.google/workbook/implementing-slos/#:~:text=We%20recommend%20defining%20this%20period%20as%20an%20integral%20number%20of%20weeks%20so%20it%20always%20contains%20the%20same%20number%20of%20weekends). The resulted setup for the static burn rate is:

|  Alarm   | Long Window | Short Window | Burn Rate Factor | Error Budget Consumed |
|:--------:|:-----------:|:------------:|:----------------:|:---------------------:|
| Critical | 30m         | 3m           | 13.44            | 1%                    |
| Minor    | 3h          | 15m          | 5.6              | 2.5%                  |
| Warning  | 1d          | 2h           | 1.12             | 4%                    |

Also note that I use different severities for each alarm. Each alarm is tagged with this severity using the [resourcegroupstaggingapi](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/resourcegroupstaggingapi/index.html) service of AWS CLI.

The multiwindow feature of the solution is implemented by defining [composite alarm](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Create_Composite_Alarm.html), for each burn-rate, that change state to ALARM only if both of the two underlying alarms, one for the long window and the other for the short one, goes into ALARM state.

Overall, for each SLO, a stack of 9 alarms is generated - 6 child alarms and 3 composite ones:

<img src="/res/cw-slo-alarms-architecture.drawio.svg"/>

In order to implement dynamic burn rates, I have defined two Lambda functions: one that calculate the current dynamic burn rate and updates the thresholds of the child alarms accordingly and the other that is triggered once a day, retrieve the current total number of events in the last SLO period and update an appropriate environment variable in the first function. The first function is triggered by three different EventBridge schedulers with rate equal to the short window of each alarm. The full architecture, which was created automatically using [cdk-dia](https://github.com/pistazie/cdk-dia) is:

<img src="/res/diagram.png"/>

### Configuration

There are 3 configuration files:
1. `burn_rates.yaml` - which configures the SLO period and the different windows and error budget consumption for each burn rate.
2. `metrics.yaml` - which configures the different metrics for each SLO type and AWS service. For now, the supported SLO types are error-rate and latency and the supported AWS services are ApiGateway and ApplicationELB.
3. `config.yaml` - In this file the user choose between static or dynamic burn rates, sets subscriptions for the SNS topic which is triggered by the alarms and declares his SLO and the requested service and its dimensions on which the SLO alarms stack should be defined. For example, if we have an API named PetStore and our error rate SLO is 99.9 % than the SLO section of the `config.yaml` file will look like:

```yaml
[99.9]
namespace: 'AWS/ApiGateway'
dimensions_map: 
  ApiName: PetStore
```
## How to Use

1. Follow the instructions in [Working with the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/work-with.html). At the *Language-specific prerequisites* section, in the above link, choose [Python prerequisites](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html), and there follow the instructions only in the prerequisites section.

2. Fork this repo

3. Clone your forked repo:
    ```
    git clone git@github.com:<your_username>/slo-alarms-with-cdk.git
    ```
4. Create a Python virtual environment

    _On MacOS or Linux_
    ```
    $ python3 -m venv .venv
    ```

    _On Windows_
    ```
    $ python -m venv .venv
    ```

5. Activate virtual environment

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

6. Install the required dependencies.

    ```
    $ pip install -r requirements.txt
    ```

7. If you are On windows replace `python3` with `python` in `cdk.json`.

8. [Create a connection to GitHub](https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html) using AWS console or CLI.

9. Edit `config.yaml` as following:
    - Choose burn rate type: static or dynamic.
    - Replace the values of the GitHub section with your forked repo ones.
    - Replace the subscriptions list with your subscriptions or delete it if you don't want any subscriptions for the SNS topic which triggered when the alarms go into IN ALARM state. Note that for firehose subscription protocol, you need to specify the arn of the role allowing access to firehose delivery stream, assuming both the firehose delivery stream and the IAM role are already exist.
    - Specify your service, dimensions and SLO.

10. Synthesize (`cdk synth`) or deploy (`cdk deploy`) the example

    ```
    $ cdk deploy
    ```
    After first `cdk deploy` [the pipeline will automatically updates itself on each push](https://docs.aws.amazon.com/cdk/v2/guide/cdk_pipeline.html#:~:text=push%0Acdk%20deploy-,Tip,-Now%20that%20you%27ve).

11. If you want to fetch future changes from this repo, follow the steps [here](https://stackoverflow.com/questions/7244321/how-do-i-update-or-sync-a-forked-repository-on-github) or in [section 6 here](https://gist.github.com/0xjac/85097472043b697ab57ba1b1c7530274).

