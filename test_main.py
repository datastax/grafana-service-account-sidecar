import unittest
from unittest.mock import patch, MagicMock
import requests_mock
from main import create_service_account, create_service_account_token, \
    ensure_grafana_token


class TestGrafanaIntegration(unittest.TestCase):

    def setUp(self):
        self.grafana_url = "http://grafana:3000"
        self.grafana_username = "admin"
        self.grafana_password = "admin"
        self.key_name = "sidecar-api-key"
        self.service_account_name = "test-sa"
        self.role = "Admin"
        self.token_name = "test-token"
        self.namespace = "default"
        self.secret_name = "grafana-token-secret"


    def test_create_service_account(self):
        with requests_mock.Mocker() as m:
            m.post(f'{self.grafana_url}/api/serviceaccounts', json={"id": 123, "name": self.service_account_name},
                   status_code=200)
            result = create_service_account(self.grafana_url, "fake_api_key", self.service_account_name, self.role)
            self.assertEqual(result["id"], 123)

    def test_create_service_account_token(self):
        with requests_mock.Mocker() as m:
            m.post(f'{self.grafana_url}/api/serviceaccounts/123/tokens', json={"key": "new_token"}, status_code=200)
            result = create_service_account_token(self.grafana_url, "fake_api_key", 123, self.token_name)
            self.assertEqual(result["key"], "new_token")

    @patch('main.config')
    @patch('main.client.CoreV1Api')
    def test_ensure_grafana_token(self, mock_v1_api, mock_config):
        mock_v1_api.return_value = MagicMock()
        with patch('main.get_or_create_grafana_api_key') as mock_get_key, \
                patch('main.create_service_account') as mock_create_sa, \
                patch('main.create_service_account_token') as mock_create_token:
            mock_get_key.return_value = "fake_api_key"
            mock_create_sa.return_value = {"id": "123"}
            mock_create_token.return_value = {"key": "new_token"}
            ensure_grafana_token(self.namespace, self.grafana_url, self.grafana_username, self.grafana_password,
                                 self.service_account_name, self.token_name, self.secret_name)
            mock_v1_api.return_value.create_namespaced_secret.assert_called_once()


if __name__ == '__main__':
    unittest.main()
