import unittest
import os
import json
from unittest.mock import MagicMock, patch, mock_open, Mock
from github import GithubException
from datetime import datetime, timezone, timedelta

from check_alerts import (
    read_event_file,
    get_pr_number,
    create_or_update_pr_comment,
    get_alert_age,
    get_thresholds_from_env,
    get_github_repo,
    get_dependabot_alerts,
    analyze_alerts,
    format_alert_output,
    post_pr_comment,
    revoke_installation_token,
    get_env_variable,
    main_check_alerts,
)

class TestGetPrNumber(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.owner.login = "test_owner"

    def test_get_pr_number_pull_request(self):
        event_name = "pull_request"
        event = {
            "pull_request": {
                "number": 123
            }
        }
        pr_number = get_pr_number(self.repo, event_name, event)
        self.assertEqual(pr_number, 123)

    def test_get_pr_number_push(self):
        event_name = "push"
        event = {
            "ref": "refs/heads/test_branch"
        }
        self.repo.get_pulls.return_value = [Mock(number=456)]
        pr_number = get_pr_number(self.repo, event_name, event)
        self.assertEqual(pr_number, 456)

    def test_get_pr_number_not_a_pull_request(self):
        event_name = "push"
        event = {
            "ref": "refs/heads/test_branch"
        }
        self.repo.get_pulls.return_value = []
        pr_number = get_pr_number(self.repo, event_name, event)
        self.assertIsNone(pr_number)

    def test_get_pr_number_missing_pull_request_event(self):
        event_name = "push"
        event = {}
        self.repo.get_pulls.return_value = []
        pr_number = get_pr_number(self.repo, event_name, event)
        self.assertIsNone(pr_number)

    def test_get_pr_number_missing_pull_request_key(self):
        event_name = "push"
        event = {"pull_request": {}}
        self.repo.get_pulls.return_value = []
        pr_number = get_pr_number(self.repo, event_name, event)
        self.assertIsNone(pr_number)

class TestReadEventFile(unittest.TestCase):
    def test_read_event_file_success(self):
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = read_event_file("dummy_path")
            self.assertEqual(result, {"key": "value"})

    def test_read_event_file_failure(self):
        with patch("builtins.open", side_effect=Exception("File not found")):
            result = read_event_file("dummy_path")
            self.assertEqual(result, {})


class TestCreateOrUpdatePRComment(unittest.TestCase):

    @patch("check_alerts.Github")
    def test_update_existing_comment(self, mock_github):
        mock_repo = Mock()
        mock_pr = Mock()
        mock_comment = Mock()
        mock_comment.body = "## Dependabot Alert Summary - Existing Comment"
        mock_pr.get_issue_comments.return_value = [mock_comment]
        mock_repo.get_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")

        mock_comment.edit.assert_called_once_with("New Comment Body")
        mock_pr.create_issue_comment.assert_not_called()

    @patch("check_alerts.Github")
    def test_create_new_comment(self, mock_github):
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.get_issue_comments.return_value = []
        mock_repo.get_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")

        mock_pr.create_issue_comment.assert_called_once_with("New Comment Body")

    @patch("check_alerts.Github")
    def test_github_exception(self, mock_github):
        mock_repo = Mock()
        mock_repo.get_pull.side_effect = GithubException(403, "Error")
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")

        # If we reached here the function handled the GithubException correctly by not raising it again

    @patch("check_alerts.Github")
    def test_other_exception(self, mock_github):
        mock_repo = Mock()
        mock_repo.get_pull.side_effect = Exception("Other Error")
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")


class TestGetAlertAge(unittest.TestCase):

    def test_get_alert_age_recent(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=2)
        self.assertEqual(get_alert_age(created_at), 2)

    def test_get_alert_age_old(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=35)
        self.assertEqual(get_alert_age(created_at), 35)

    def test_get_alert_age_same_day(self):
        created_at = datetime.now(timezone.utc) - timedelta(hours=5)
        self.assertEqual(get_alert_age(created_at), 0)

    def test_get_alert_age_future(self):
        created_at = datetime.now(timezone.utc) + timedelta(days=1)
        self.assertEqual(get_alert_age(created_at), -1)


class TestGetThresholdsFromEnv(unittest.TestCase):

    @patch.dict(
        os.environ,
        {
            "INPUT_CRITICAL_THRESHOLD": "1",
            "INPUT_HIGH_THRESHOLD": "2",
            "INPUT_MEDIUM_THRESHOLD": "7",
            "INPUT_LOW_THRESHOLD": "15",
        },
    )
    def test_get_thresholds_from_env_set(self):
        expected_thresholds = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 7, "LOW": 15}
        self.assertEqual(get_thresholds_from_env(), expected_thresholds)

    @patch.dict(os.environ, {})
    def test_get_thresholds_from_env_default(self):
        expected_thresholds = {"CRITICAL": 3, "HIGH": 5, "MEDIUM": 14, "LOW": 30}
        self.assertEqual(get_thresholds_from_env(), expected_thresholds)

    @patch.dict(os.environ, {"INPUT_CRITICAL_THRESHOLD": "invalid"})
    def test_get_thresholds_from_env_invalid_input(self):
        with self.assertRaises(ValueError):
            get_thresholds_from_env()


class TestGetGithubRepo(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test_org/test_repo"})
    @patch("check_alerts.Github")
    def test_get_github_repo_success(self, mock_github):
        mock_repo = Mock()
        mock_repo.full_name = "test_org/test_repo"
        mock_github.get_repo.return_value = mock_repo

        repo = get_github_repo(mock_github)

        self.assertEqual(repo.full_name, "test_org/test_repo")

    @patch("check_alerts.os.getenv")
    @patch("check_alerts.sys.exit")
    def test_get_github_repo_no_repo_name(self, mock_exit, mock_getenv):
        mock_getenv.return_value = None
        mock_github = MagicMock()

        get_github_repo(mock_github)

        mock_exit.assert_called_once_with(1)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test_org/test_repo"})
    @patch("check_alerts.Github")
    def test_get_github_repo_github_exception(self, mock_github):
        mock_github.get_repo.side_effect = GithubException(404, "Repo not found")

        with self.assertRaises(GithubException):
            get_github_repo(mock_github)

class TestGetDependabotAlerts(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()

    def test_get_dependabot_alerts_success(self):
        mock_alerts = ["alert1", "alert2"]
        self.repo.get_dependabot_alerts.return_value = mock_alerts

        alerts = get_dependabot_alerts(self.repo)
        self.assertEqual(alerts, mock_alerts)
        self.repo.get_dependabot_alerts.assert_called_once()

    def test_get_dependabot_alerts_github_exception(self):
        self.repo.get_dependabot_alerts.side_effect = GithubException(403, {"message": "Forbidden"})

        with self.assertRaises(SystemExit) as cm:
            get_dependabot_alerts(self.repo)
        self.assertEqual(cm.exception.code, 1)
        self.repo.get_dependabot_alerts.assert_called_once()

    def test_get_dependabot_alerts_general_exception(self):
        self.repo.get_dependabot_alerts.side_effect = Exception("General error")

        with self.assertRaises(Exception) as cm:
            get_dependabot_alerts(self.repo)
        self.assertEqual(str(cm.exception), "General error")
        self.repo.get_dependabot_alerts.assert_called_once()

    def test_get_dependabot_alerts_disabled(self):
        self.repo.get_dependabot_alerts.side_effect = GithubException(
            403,
            {
                "message": "Dependabot alerts are disabled for this repository.",
                "documentation_url": "https://docs.github.com/rest/dependabot/alerts#list-dependabot-alerts-for-a-repository",
                "status": "403"
            }
        )

        alerts = get_dependabot_alerts(self.repo)
        self.assertEqual(alerts, [])
        self.repo.get_dependabot_alerts.assert_called_once()

class TestAnalyzeAlerts(unittest.TestCase):
    def setUp(self):
        self.alerts = [
            Mock(
                state="open",
                security_advisory=Mock(severity="high", summary="Test summary"),
                created_at=datetime.now(timezone.utc) - timedelta(days=10),
                dependency=Mock(package=Mock()),
                html_url="http://example.com"
            ),
            Mock(
                state="closed",
                security_advisory=Mock(severity="low", summary="Test summary 2"),
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
                dependency=Mock(package=Mock()),
                html_url="http://example.com/2"
            ),
            Mock(
                state="open",
                security_advisory=Mock(severity="low", summary="Test summary 2"),
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
                dependency=Mock(package=Mock()),
                html_url="http://example.com/2"
            )
        ]
        self.alert_thresholds = {
            "CRITICAL": 3,
            "HIGH": 5,
            "MEDIUM": 14,
            "LOW": 30,
        }

        # Ensure the name attribute returns the correct value
        self.alerts[0].dependency.package.name = "test_package"
        self.alerts[1].dependency.package.name = "test_package_2"
        self.alerts[2].dependency.package.name = "test_package_3"

    def test_analyze_alerts(self):
        violations, all_alerts = analyze_alerts(self.alerts, self.alert_thresholds)

        self.assertEqual(len(all_alerts), 2)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["package"], "test_package")
        self.assertEqual(violations[0]["severity"], "HIGH")
        self.assertEqual(violations[0]["age_days"], 10)
        self.assertEqual(violations[0]["threshold_days"], 5)
        self.assertEqual(violations[0]["url"], "http://example.com")
        self.assertEqual(violations[0]["title"], "Test summary")

    def test_analyze_alerts_no_violations(self):
        self.alerts[0].created_at = datetime.now(timezone.utc) - timedelta(days=3)
        violations, all_alerts = analyze_alerts(self.alerts, self.alert_thresholds)

        self.assertEqual(len(all_alerts), 2)
        self.assertEqual(len(violations), 0)

    def test_analyze_alerts_all_closed(self):
        self.alerts[0].state = "closed"
        self.alerts[2].state = "closed"
        violations, all_alerts = analyze_alerts(self.alerts, self.alert_thresholds)

        self.assertEqual(len(all_alerts), 0)
        self.assertEqual(len(violations), 0)

class TestFormatAlertOutput(unittest.TestCase):
    def setUp(self):
        self.violations = [
            {
                "package": "test_package",
                "severity": "HIGH",
                "age_days": 10,
                "threshold_days": 5,
                "url": "http://example.com",
                "title": "Test summary",
                "created_at": "2025-02-01 12:00:00 UTC"
            }
        ]
        self.all_alerts = [
            {
                "package": "test_package",
                "severity": "HIGH",
                "age_days": 10,
                "threshold_days": 5,
                "url": "http://example.com",
                "title": "Test summary",
                "created_at": "2025-02-01 12:00:00 UTC"
            },
            {
                "package": "test_package_2",
                "severity": "LOW",
                "age_days": 3,
                "threshold_days": 30,
                "url": "http://example.com/2",
                "title": "Test summary 2",
                "created_at": "2025-02-07 12:00:00 UTC"
            }
        ]

    def test_format_alert_output_with_violations(self):
        report_mode = False
        output = format_alert_output(self.violations, self.all_alerts, report_mode)
        expected_output = (
            "## Dependabot Alert Summary\n"
            "Total open alerts: 2\n"
            "Alerts exceeding age threshold: 1\n"
            "\n### :x: Violations (Alerts exceeding threshold)\n"
            "\n\n#### \n"
            "- **Severity:** HIGH\n"
            "- **Age:** 10 days (Threshold: 5 days)\n"
            "- **Created:** 2025-02-01 12:00:00 UTC\n"
            "- **URL:** http://example.com\n"
            "\n:no_entry: Action failed due to alerts exceeding age thresholds"
        )
        self.assertEqual(output, expected_output)

    def test_format_alert_output_with_violations_report_mode(self):
        report_mode = True
        output = format_alert_output(self.violations, self.all_alerts, report_mode)
        expected_output = (
            "## Dependabot Alert Summary\n"
            "Total open alerts: 2\n"
            "Alerts exceeding age threshold: 1\n"
            "\n### :x: Violations (Alerts exceeding threshold)\n"
            "\n\n#### \n"
            "- **Severity:** HIGH\n"
            "- **Age:** 10 days (Threshold: 5 days)\n"
            "- **Created:** 2025-02-01 12:00:00 UTC\n"
            "- **URL:** http://example.com\n"
            "\n:warning: Alerts exceed age thresholds but running in report mode"
        )
        self.assertEqual(output, expected_output)

    def test_format_alert_output_no_violations(self):
        report_mode = False
        output = format_alert_output([], self.all_alerts, report_mode)
        expected_output = (
            "## Dependabot Alert Summary\n"
            "Total open alerts: 2\n"
            "Alerts exceeding age threshold: 0\n"
            "\n:white_check_mark: All alerts are within acceptable age thresholds"
        )
        self.assertEqual(output, expected_output)

class TestPostPrComment(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.pr_number = 123
        self.output = "Test output"

    @patch('check_alerts.create_or_update_pr_comment')
    def test_post_pr_comment_success(self, mock_create_or_update_pr_comment):
        post_pr_comment(self.repo, self.pr_number, self.output)
        mock_create_or_update_pr_comment.assert_called_once_with(self.repo, self.pr_number, self.output)

    @patch('check_alerts.create_or_update_pr_comment')
    def test_post_pr_comment_no_pr_number(self, mock_create_or_update_pr_comment):
        post_pr_comment(self.repo, None, self.output)
        mock_create_or_update_pr_comment.assert_not_called()

    @patch('check_alerts.create_or_update_pr_comment')
    def test_post_pr_comment_github_exception(self, mock_create_or_update_pr_comment):
        mock_exception = GithubException(status=403, message="Test exception")
        mock_create_or_update_pr_comment.side_effect = mock_exception
        with self.assertRaises(GithubException):
            post_pr_comment(self.repo, self.pr_number, self.output)

    @patch('check_alerts.create_or_update_pr_comment')
    def test_post_pr_comment_general_exception(self, mock_create_or_update_pr_comment):
        mock_create_or_update_pr_comment.side_effect = Exception("Test exception")
        with self.assertRaises(Exception):
            post_pr_comment(self.repo, self.pr_number, self.output)


class TestRevokeInstallationToken(unittest.TestCase):
    def test_revoke_installation_token(self):
        mock_github = MagicMock()
        mock_requester = MagicMock()
        mock_github.requester = mock_requester
        mock_requester.requestJsonAndCheck.return_value = (
            "headers",
            json.dumps({"Status": 204}),
        )

        revoke_installation_token(mock_github)

        mock_requester.requestJsonAndCheck.assert_called_once_with(
            "DELETE", "/installation/token"
        )

    @patch("check_alerts.sys.exit")
    def test_revoke_installation_token_failure(self, mock_exit):
        mock_github = MagicMock()
        mock_requester = MagicMock()
        mock_github.requester = mock_requester
        mock_requester.requestJsonAndCheck.side_effect = GithubException("Error")

        revoke_installation_token(mock_github)

        mock_requester.requestJsonAndCheck.assert_called_once_with(
            "DELETE", "/installation/token"
        )
        mock_exit.assert_called_once_with(1)

class TestGetEnvVariable(unittest.TestCase):
    @patch('check_alerts.os.getenv')
    def test_get_env_variable_success(self, mock_getenv):
        mock_getenv.return_value = "test_value"
        result = get_env_variable("TEST_ENV_VAR")
        self.assertEqual(result, "test_value")
        mock_getenv.assert_called_once_with("TEST_ENV_VAR", None)

    @patch('check_alerts.os.getenv')
    def test_get_env_variable_with_default(self, mock_getenv):
        mock_getenv.return_value = "default_value"
        result = get_env_variable("TEST_ENV_VAR", "default_value")
        self.assertEqual(result, "default_value")
        mock_getenv.assert_called_once_with("TEST_ENV_VAR", "default_value")

    @patch('check_alerts.os.getenv')
    def test_get_env_variable_not_found(self, mock_getenv):
        mock_getenv.return_value = None
        with self.assertRaises(SystemExit) as cm:
            get_env_variable("TEST_ENV_VAR")
        self.assertEqual(cm.exception.code, 1)
        mock_getenv.assert_called_once_with("TEST_ENV_VAR", None)

class TestMainCheckAlerts(unittest.TestCase):
    @patch('check_alerts.get_dependabot_alerts')
    @patch('check_alerts.analyze_alerts')
    @patch('check_alerts.format_alert_output')
    @patch('check_alerts.read_event_file')
    @patch('check_alerts.get_pr_number')
    @patch('check_alerts.post_pr_comment')
    @patch('check_alerts.revoke_installation_token')
    def test_main_check_alerts_success(
        self, mock_revoke_installation_token, mock_post_pr_comment, mock_get_pr_number, mock_read_event_file,
        mock_format_alert_output, mock_analyze_alerts, mock_get_dependabot_alerts
    ):
        github = Mock()
        repo = Mock()
        alert_thresholds = {"HIGH": 5}
        report_mode = False
        event_name = "pull_request"
        event_path = "test_event_path"

        mock_get_dependabot_alerts.return_value = []
        mock_analyze_alerts.return_value = ([], [])
        mock_format_alert_output.return_value = "Test output"
        mock_read_event_file.return_value = {}
        mock_get_pr_number.return_value = 123

        with patch('sys.exit') as mock_exit:
            main_check_alerts(
                github, repo, alert_thresholds, report_mode, event_name, event_path
            )
            mock_exit.assert_called_once_with(0)

    @patch('check_alerts.get_dependabot_alerts')
    @patch('check_alerts.analyze_alerts')
    @patch('check_alerts.format_alert_output')
    @patch('check_alerts.read_event_file')
    @patch('check_alerts.get_pr_number')
    @patch('check_alerts.post_pr_comment')
    @patch('check_alerts.revoke_installation_token')
    def test_main_check_alerts_with_violations(
        self, mock_revoke_installation_token, mock_post_pr_comment, mock_get_pr_number, mock_read_event_file,
        mock_format_alert_output, mock_analyze_alerts, mock_get_dependabot_alerts
    ):
        github = Mock()
        repo = Mock()
        alert_thresholds = {"HIGH": 5}
        report_mode = False
        event_name = "pull_request"
        event_path = "test_event_path"

        mock_get_dependabot_alerts.return_value = []
        mock_analyze_alerts.return_value = ([{"severity": "HIGH"}], [])
        mock_format_alert_output.return_value = "Test output"
        mock_read_event_file.return_value = {}
        mock_get_pr_number.return_value = 123

        with patch('sys.exit') as mock_exit:
            main_check_alerts(
                github, repo, alert_thresholds, report_mode, event_name, event_path
            )
            # we have mocked the sys.exit,
            #  so the flow results in exit called with 1,
            #  and *then* exit called with 0
            mock_exit.assert_any_call(1)
            mock_exit.assert_called_with(0)

    @patch('check_alerts.get_dependabot_alerts')
    @patch('check_alerts.analyze_alerts')
    @patch('check_alerts.format_alert_output')
    @patch('check_alerts.read_event_file')
    @patch('check_alerts.get_pr_number')
    @patch('check_alerts.post_pr_comment')
    @patch('check_alerts.revoke_installation_token')
    def test_main_check_alerts_report_mode(
        self, mock_revoke_installation_token, mock_post_pr_comment, mock_get_pr_number, mock_read_event_file,
        mock_format_alert_output, mock_analyze_alerts, mock_get_dependabot_alerts
    ):
        github = Mock()
        repo = Mock()
        alert_thresholds = {"HIGH": 5}
        report_mode = True
        event_name = "pull_request"
        event_path = "test_event_path"

        mock_get_dependabot_alerts.return_value = []
        mock_analyze_alerts.return_value = ([{"severity": "HIGH"}], [])
        mock_format_alert_output.return_value = "Test output"
        mock_read_event_file.return_value = {}
        mock_get_pr_number.return_value = 123

        with patch('sys.exit') as mock_exit:
            main_check_alerts(
                github, repo, alert_thresholds, report_mode, event_name, event_path
            )
            mock_exit.assert_called_once_with(0)
