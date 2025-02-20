#!/usr/bin/env python3
import os
import json
from datetime import datetime, timezone
from github import Auth, Github, GithubException, Repository
import sys


def read_event_file(event_path):
    try:
        with open(event_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading event file: {e}")
        return {}

def get_pr_number(repo, event_name, event):
    if event_name == "pull_request":
        print("This is a Pull Request")
        pr_number = event.get("pull_request", {}).get("number")
        if pr_number:
            return pr_number

    elif event_name == "push":
        print("This is a Push event")
        ref = event.get("ref")

        if ref and ref.startswith("refs/heads/"):
            branch_name = ref[len("refs/heads/"):]
            print(f"Branch name: {branch_name}")
            print(f"Owner: {repo.owner.login}")
            pulls = repo.get_pulls(state="open", head=f"{repo.owner.login}:{branch_name}")
            for pr in pulls:
                return pr.number

    print("Not a pull request")
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
        alerts = repo.get_dependabot_alerts(state="open")
        alerts_list = list(alerts)
        print(f"Returned {len(alerts_list)} alerts")
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
    except Exception as e:
        print(f"Error: {e}")
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
        dependency = alert.dependency
        package = dependency.package

        alert_info = {
            "package": package.name,
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
        except GithubException as e:
            print(f"Error posting comment to PR: {e}")
            if e.status == 403:
                print("Error: Insufficient permissions to post PR comments")
                print("Please ensure workflow has 'pull-requests: write' permission")
            raise
        except Exception as e:
            print(f"Error posting comment to PR: {e}")
            raise

def revoke_installation_token(github: Github):
    print("Completed: revoking token")
    try:
        github.requester.requestJsonAndCheck("DELETE", "/installation/token")
    except GithubException as e:
        print(f"Error revoking installation token: {e}")
        sys.exit(1)

def get_env_variable(name, default=None):
    value = os.getenv(name, default)
    if value is None:
        print(f"Error: {name} not found")
        sys.exit(1)
    return value

def main_check_alerts(
    github, repo, alert_thresholds, report_mode, event_name, event_path
):
    alerts = get_dependabot_alerts(repo)
    violations, all_alerts = analyze_alerts(alerts, alert_thresholds)
    output = format_alert_output(violations, all_alerts, report_mode)

    event = read_event_file(event_path)
    pr_number = get_pr_number(repo, event_name, event)
    post_pr_comment(repo, pr_number, output)

    revoke_installation_token(github)

    if violations and not report_mode:
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    private_key = get_env_variable("PRIVATE_KEY").replace("\\n", "\n")
    app_id = get_env_variable("APP_ID")
    installation_id = get_env_variable("INSTALLATION_ID")

    auth = Auth.AppAuth(app_id, private_key).get_installation_auth(int(installation_id))
    github = Github(auth=auth)

    repo = get_github_repo(github)

    alert_thresholds = get_thresholds_from_env()
    report_mode = os.getenv("INPUT_REPORT_MODE", "false").lower() == "true"

    event_name = get_env_variable("GITHUB_EVENT_NAME")
    event_path = get_env_variable("GITHUB_EVENT_PATH")

    main_check_alerts(
        github, repo, alert_thresholds, report_mode, event_name, event_path
    )
