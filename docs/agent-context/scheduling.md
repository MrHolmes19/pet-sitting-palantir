# Scheduling

## Chosen Scheduler

Use AWS EventBridge Scheduler to invoke an AWS Lambda function every 5 minutes
in the AWS Asia Pacific Sydney region (`ap-southeast-2`).

The Lambda function should call the existing Python due-scope runner instead of
moving scheduler logic into AWS:

```bash
python -m pet_sitting_palantir --run-due --max-pages all --pretty
```

GitHub Actions remains useful for CI and deployment, but not for production
timekeeping.

## Why AWS EventBridge Scheduler And Lambda

This is the best fit for alert-grade Auckland notifications because it provides:

- A managed 5-minute scheduler instead of GitHub Actions' best-effort scheduled
  workflow queue.
- A nearby, mature AWS region (`ap-southeast-2`) for Scheduler and Lambda.
- No always-on server to patch, monitor, or restart.
- Low expected cost under AWS free allowances for one 5-minute personal scraper.
- A small code adaptation path: add a Lambda handler around the current Python
  workflow rather than rewriting the scraper.
- A clean GitHub update flow: GitHub Actions can deploy code changes to Lambda
  on push while EventBridge keeps the production schedule.

The first implementation should try a normal Lambda zip deployment. The current
dependency set is small enough that a zip package is likely simpler and cheaper
than a Lambda container image. Use a container image only if dependency packaging
or native binary compatibility makes the zip path brittle.

## Free-Tier Operating Decisions

AWS is not a perfect hard-capped free platform. Budgets and free-tier alerts are
warnings, not a guaranteed kill switch. The production scheduler should stay
within the free tier by keeping the AWS surface deliberately small.

Current expected free allowances are enough for this workload:

- EventBridge Scheduler provides 14,000,000 free invocations per month. A
  5-minute schedule is about 8,640 invocations per month.
- Lambda provides 1,000,000 free requests and 400,000 GB-seconds per month. At
  512 MB memory, this is enough for roughly 90 seconds per 5-minute invocation
  across a 30-day month.
- CloudWatch Logs provides 5 GB per month across ingestion, archive storage, and
  Logs Insights data scanned. This should be enough if logs stay compact.

Decisions:

- Use `ap-southeast-2`.
- Start Lambda at 512 MB memory.
- Set Lambda timeout below the hard 15-minute maximum, initially 5 to 10 minutes.
- Set Lambda reserved concurrency to 1 so runs cannot overlap or fan out.
- Configure EventBridge Scheduler with a low retry count, initially 0 or 1.
- Set CloudWatch log retention to 30 days. Keep logs concise so retention remains
  inside the 5 GB monthly CloudWatch Logs free allowance.
- Do not put the Lambda in a VPC unless there is a concrete need. A NAT gateway
  would create unnecessary cost.
- Use Lambda zip deployment first. Avoid ECR/container images for v1 unless zip
  packaging fails because of dependency compatibility.
- Store runtime secrets in Lambda environment variables initially. Avoid Secrets
  Manager for v1 because it adds cost and operational surface.
- Do not enable provisioned concurrency, Lambda durable functions, Lambda managed
  instances, X-Ray, custom CloudWatch dashboards, or paid observability features
  for v1.
- Do not log raw HTML, full listing payload dumps, database URLs, Telegram tokens,
  or other secret values.

Lambda environment variables are acceptable for v1 runtime configuration. Lambda
encrypts environment variables at rest with an AWS managed KMS key by default,
and AWS does not charge for that default key. Users with enough Lambda/IAM access
can still view or manage these values, so keep AWS account access narrow and
avoid printing them in logs.

Expected Lambda environment variables:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Deployment Shape

Target flow:

```text
push to main
GitHub Actions runs targeted tests
GitHub Actions builds Lambda zip package
GitHub Actions updates the Lambda function code/configuration
EventBridge Scheduler invokes Lambda every 5 minutes
Lambda runs the due-scope workflow
```

The scheduled Lambda should receive no scope-specific configuration from
EventBridge. Scope cadence stays in PostgreSQL and is evaluated by the app.

## Implementation Steps

1. Add a Lambda handler module that loads settings and calls the existing
   due-scope workflow.
2. Add packaging scripts or CI steps to build a Lambda-compatible zip with
   project code and dependencies.
3. Create the Lambda function in `ap-southeast-2` with Python 3.12, 512 MB
   memory, a 5 to 10 minute timeout, reserved concurrency 1, environment
   variables, and 30-day CloudWatch log retention.
4. Create an EventBridge Scheduler rule in `ap-southeast-2` with
   `rate(5 minutes)`, flexible time window off, and a low retry count.
5. Deploy from GitHub Actions using OIDC or narrowly scoped AWS credentials.
6. Verify one manual Lambda invocation against the production database.
7. Enable the schedule and watch CloudWatch logs, Lambda duration, Lambda errors,
   and database `scrape_runs` for at least the first hour.
8. Keep the old GitHub scheduled workflow disabled or remove its `schedule`
   trigger once AWS scheduling is live.

## Alternatives Considered

GitHub Actions schedule was rejected for alert-grade timing. The workflow
accepted `*/5 * * * *`, but observed production gaps were far larger than 5
minutes. GitHub documents scheduled workflow delays and possible dropped queued
jobs under high load.

Google Cloud Free Tier VM was rejected as the primary path because the always-free
Compute Engine VM is limited to selected US regions. It is still a workable low
migration fallback if region and server maintenance are acceptable.

Google Cloud Scheduler was not chosen for v1. Its free tier is based on jobs, not
executions, so one 5-minute job can fit the free scheduler allowance. However,
running this Python scraper would still require a target such as Cloud Run,
another function platform, or a VM. That is not better than AWS Lambda for this
project.

Supabase scheduled Edge Functions were rejected because they would require
rewriting the Python scraper into the Supabase Edge runtime shape.

Oracle Always Free compute was rejected because quiet periodic workloads can look
idle, and Oracle documents that idle Always Free compute instances may be
reclaimed.

PythonAnywhere free scheduled tasks are not suitable for new accounts or
5-minute cadence.

Heroku no longer offers free dynos.

Home hardware such as a Raspberry Pi, old thin client, or phone is technically
valid and may provide a residential New Zealand IP, but it is not cloud-free
unless hardware already exists and it shifts reliability to home power and
networking.

Cheap VPS providers are operationally simple, but they are not free.

## References

- AWS Lambda free tier: https://aws.amazon.com/pm/lambda/
- AWS EventBridge Scheduler pricing: https://aws.amazon.com/eventbridge/pricing/
- AWS CloudWatch pricing: https://aws.amazon.com/cloudwatch/pricing/
- AWS Lambda endpoints: https://docs.aws.amazon.com/general/latest/gr/lambda-service.html
- AWS EventBridge Scheduler endpoints: https://docs.aws.amazon.com/general/latest/gr/eventbridgescheduler.html
- AWS Lambda Python zip packages: https://docs.aws.amazon.com/lambda/latest/dg/python-package.html
- AWS Lambda environment variable encryption: https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars-encryption.html
