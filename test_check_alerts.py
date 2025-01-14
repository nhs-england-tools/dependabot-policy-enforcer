import unittest
import os
import json
from unittest.mock import patch, mock_open, Mock
from github import GithubException

from check_alerts import get_pr_number, create_or_update_pr_comment

class TestGetPRNumber(unittest.TestCase):

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': '/path/to/event.json'})
    @patch('builtins.open', new_callable=mock_open, read_data='{"pull_request": {"number": 123}}')
    def test_get_pr_number_success(self, mock_file):
        self.assertEqual(get_pr_number(), 123)

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': '/path/to/event.json'})
    @patch('builtins.open', new_callable=mock_open, read_data='{}')
    def test_get_pr_number_no_pull_request_key(self, mock_file):
        self.assertIsNone(get_pr_number())

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': '/path/to/event.json'})
    @patch('builtins.open', new_callable=mock_open, read_data='{"pull_request": {}}')
    def test_get_pr_number_no_number_key(self, mock_file):
        self.assertIsNone(get_pr_number())

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push'})
    def test_get_pr_number_not_pull_request(self):
        self.assertIsNone(get_pr_number())

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request'})
    def test_get_pr_number_no_event_path(self):
        self.assertIsNone(get_pr_number())

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': '/path/to/event.json'})
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_get_pr_number_file_not_found(self, mock_file):
        self.assertIsNone(get_pr_number())


    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': '/path/to/event.json'})
    @patch('builtins.open', new_callable=mock_open, read_data='{"pull_request": {"number": "123"}}')
    def test_get_pr_number_string_number(self, mock_file):
        self.assertEqual(get_pr_number(), "123")

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': '/path/to/event.json'})
    @patch('builtins.open', new_callable=mock_open, read_data='invalid json')
    def test_get_pr_number_invalid_json(self, mock_file):
        self.assertIsNone(get_pr_number())



class TestCreateOrUpdatePRComment(unittest.TestCase):

    @patch('check_alerts.Github')
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

    @patch('check_alerts.Github')
    def test_create_new_comment(self, mock_github):
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.get_issue_comments.return_value = []
        mock_repo.get_pull.return_value = mock_pr
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")

        mock_pr.create_issue_comment.assert_called_once_with("New Comment Body")


    @patch('check_alerts.Github')
    def test_github_exception(self, mock_github):
        mock_repo = Mock()
        mock_repo.get_pull.side_effect = GithubException(403, "Error")
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")


        # If we reached here the function handled the GithubException correctly by not raising it again

    @patch('check_alerts.Github')
    def test_other_exception(self, mock_github):
        mock_repo = Mock()
        mock_repo.get_pull.side_effect = Exception("Other Error")
        mock_github.return_value.get_repo.return_value = mock_repo

        create_or_update_pr_comment(mock_repo, 1, "New Comment Body")
        # same as the github exception

