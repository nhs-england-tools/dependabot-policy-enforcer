#!/usr/bin/env python3
import os
import json
from datetime import datetime, timezone
from github import Auth, Github, GithubException
import sys


def get_pr_number():
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        try:
            event_path = os.getenv("GITHUB_EVENT_PATH")
            if event_path:
                with open(event_path) as f:
                    event = json.load(f)
                    pr_number = event.get("pull_request", {}).get("number")
                    if pr_number:
                        return pr_number
        except Exception as e:
            print(f"Error reading event file: {e}")
    return None


def create_or_update_pr_comment(repo, pr_number, body):
    try:
        pr = repo.get_pull(pr_number)
        # Look for existing bot comment
        for comment in pr.get_issue_comments():
            if "## Dependabot Alert Summary" in comment.body:
                print("Updating existing comment")
                comment.edit(body)
                return
        # No existing comment found, create new one
        print("Creating new comment")
        pr.create_issue_comment(body)
    except GithubException as e:
        print(f"Error posting comment to PR: {e}")
        return
    except Exception as e:
        print(f"Error posting comment to PR: {e}")
        return


def get_alert_age(created_at):
    now = datetime.now(timezone.utc)
    age = now - created_at
    return age.days


def get_thresholds_from_env():
    return {
        "CRITICAL": int(os.getenv("INPUT_CRITICAL_THRESHOLD", "3")),
        "HIGH": int(os.getenv("INPUT_HIGH_THRESHOLD", "5")),
        "MEDIUM": int(os.getenv("INPUT_MEDIUM_THRESHOLD", "14")),
        "LOW": int(os.getenv("INPUT_LOW_THRESHOLD", "30")),
    }


def get_github_repo(github: Github):
    repo_name = os.getenv("GITHUB_REPOSITORY")

    if not repo_name:
        print("Error: GITHUB_REPOSITORY not found")
        sys.exit(1)

    print(f"Checking alerts for repository: {repo_name}")

    repo = github.get_repo(repo_name)
    print(f"Repository: {repo.full_name}")

    return repo


def get_dependabot_alerts(repo):
    try:
        alerts = repo.get_dependabot_alerts()
        return alerts
    except GithubException as e:
        print(f"Error: {e}")
        if e.status == 403:
            print("Error: Insufficient permissions to access Dependabot alerts")
            print("Please ensure:")
            print("1. GITHUB_TOKEN has 'security_events' permission")
            print("2. Workflow has 'security-events: read' permission")
            print("3. Dependabot alerts are enabled for this repository")
            sys.exit(1)
        raise


def analyze_alerts(alerts, ALERT_THRESHOLDS):
    violations = []
    all_alerts = []
    for alert in alerts:
        if not alert.state == "open":
            continue

        severity = alert.security_advisory.severity.upper()
        age = get_alert_age(alert.created_at)
        threshold = ALERT_THRESHOLDS.get(severity)

        alert_info = {
            "package": alert.dependency.package.name,
            "severity": severity,
            "age_days": age,
            "threshold_days": threshold,
            "url": alert.html_url,
            "title": alert.security_advisory.summary,
            "created_at": alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

        all_alerts.append(alert_info)

        if age > threshold:
            violations.append(alert_info)
    return violations, all_alerts


def format_alert_output(violations, all_alerts, REPORT_MODE):
    output = []
    output.append("## Dependabot Alert Summary")
    output.append(f"Total open alerts: {len(all_alerts)}")
    output.append(f"Alerts exceeding age threshold: {len(violations)}")

    if violations:
        output.append("\n### :x: Violations (Alerts exceeding threshold)")
        for violation in violations:
            output.append(f"\n\n#### ")
            output.append(f"- **Severity:** {violation['severity']}")
            output.append(
                f"- **Age:** {violation['age_days']} days (Threshold: {violation['threshold_days']} days)"
            )
            output.append(f"- **Created:** {violation['created_at']}")
            output.append(f"- **URL:** {violation['url']}")

        if REPORT_MODE:
            output.append(
                "\n:warning: Alerts exceed age thresholds but running in report mode"
            )
        else:
            output.append(
                "\n:no_entry: Action failed due to alerts exceeding age thresholds"
            )
    else:
        output.append(
            "\n:white_check_mark: All alerts are within acceptable age thresholds"
        )
    return "\n".join(output)


def post_pr_comment(repo, pr_number, output):
    if pr_number:
        try:
            create_or_update_pr_comment(repo, int(pr_number), output)
        except Exception as e:
            print(f"Error posting comment to PR: {e}")
            if e.status == 403:
                print("Error: Insufficient permissions to post PR comments")
                print("Please ensure workflow has 'pull-requests: write' permission")


def revoke_installation_token(github: Github):
    requester = github.requester
    _, response = requester.requestJsonAndCheck("DELETE", "/installation/token")

    json_response = json.loads(response)

    print(f"Revoke endpoint response: {json_response}")

    if json_response["Status"] != 204:
        print("Failed to revoke installation token")
        sys.exit(1)


def main_check_alerts():
    private_key = os.getenv("PRIVATE_KEY").replace("\\n", "\n")
    app_id = os.getenv("APP_ID")
    installation_id = os.getenv("INSTALLATION_ID")

    missing_vars = []

    if not private_key:
        missing_vars.append("PRIVATE_KEY")

    if not app_id:
        missing_vars.append("APP_ID")

    if not installation_id:
        missing_vars.append("INSTALLATION_ID")

    if missing_vars:
        for var in missing_vars:
            print(f"Error: {var} not found")
        sys.exit(1)

    auth = Auth.AppAuth(app_id, private_key).get_installation_auth(int(installation_id))
    github = Github(auth=auth)

    repo = get_github_repo(github)

    ALERT_THRESHOLDS = get_thresholds_from_env()
    REPORT_MODE = os.getenv("INPUT_REPORT_MODE", "false").lower() == "true"

    alerts = get_dependabot_alerts(repo)
    violations, all_alerts = analyze_alerts(alerts, ALERT_THRESHOLDS)
    output = format_alert_output(violations, all_alerts, REPORT_MODE)

    pr_number = get_pr_number()
    post_pr_comment(repo, pr_number, output)

    revoke_installation_token(github)

    if violations and not REPORT_MODE:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main_check_alerts()
