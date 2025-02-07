import unittest
import os
import json
from unittest.mock import MagicMock, patch, mock_open, Mock
from github import GithubException
from datetime import datetime, timezone, timedelta

from check_alerts import (
    get_pr_number,
    create_or_update_pr_comment,
    get_alert_age,
    get_thresholds_from_env,
    get_github_repo,
    revoke_installation_token,
)


class TestGetPRNumber(unittest.TestCase):

    @patch.dict(
        os.environ,
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "/path/to/event.json",
        },
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"pull_request": {"number": 123}}',
    )
    def test_get_pr_number_success(self, mock_file):
        self.assertEqual(get_pr_number(), 123)

    @patch.dict(
        os.environ,
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "/path/to/event.json",
        },
    )
    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    def test_get_pr_number_no_pull_request_key(self, mock_file):
        self.assertIsNone(get_pr_number())

    @patch.dict(
        os.environ,
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "/path/to/event.json",
        },
    )
    @patch("builtins.open", new_callable=mock_open, read_data='{"pull_request": {}}')
    def test_get_pr_number_no_number_key(self, mock_file):
        self.assertIsNone(get_pr_number())

    @patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"})
    def test_get_pr_number_not_pull_request(self):
        self.assertIsNone(get_pr_number())

    @patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request"})
    def test_get_pr_number_no_event_path(self):
        self.assertIsNone(get_pr_number())

    @patch.dict(
        os.environ,
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "/path/to/event.json",
        },
    )
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_get_pr_number_file_not_found(self, mock_file):
        self.assertIsNone(get_pr_number())

    @patch.dict(
        os.environ,
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "/path/to/event.json",
        },
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"pull_request": {"number": "123"}}',
    )
    def test_get_pr_number_string_number(self, mock_file):
        self.assertEqual(get_pr_number(), "123")

    @patch.dict(
        os.environ,
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "/path/to/event.json",
        },
    )
    @patch("builtins.open", new_callable=mock_open, read_data="invalid json")
    def test_get_pr_number_invalid_json(self, mock_file):
        self.assertIsNone(get_pr_number())


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
        # Arrange
        mock_getenv.return_value = None
        mock_github = MagicMock()

        # Act
        get_github_repo(mock_github)

        # Assert
        mock_exit.assert_called_once_with(1)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test_org/test_repo"})
    @patch("check_alerts.Github")
    def test_get_github_repo_github_exception(self, mock_github):
        mock_github.get_repo.side_effect = GithubException(404, "Repo not found")

        with self.assertRaises(GithubException):
            get_github_repo(mock_github)


class TestRevokeInstallationToken(unittest.TestCase):
    @patch("check_alerts.Github")
    def test_revoke_installation_token(self, mock_github):
        mock_github = mock_github.return_value
        mock_requester = MagicMock()
        mock_github.requester.return_value = mock_requester
        mock_requester.requestJsonAndCheck.return_value = (
            "headers",
            json.dumps({"Status": 204}),
        )

        revoke_installation_token(mock_github)

        mock_requester.requestJsonAndCheck.assert_called_once_with(
            "DELETE", "/installation/token"
        )
