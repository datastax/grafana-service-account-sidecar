import time
import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import base64
import os
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_service_account(grafana_url, grafana_username, grafana_password, service_account_name, role="Admin"):
    """Ensure a Grafana service account exists or create one if it doesn't."""
    auth = (grafana_username, grafana_password)
    headers = {'Content-Type': 'application/json'}

    # Search for the specific service account
    search_url = f"{grafana_url}/api/serviceaccounts/search?perpage=10&page=1&query={service_account_name}"
    response = requests.get(search_url, auth=auth, headers=headers)
    response.raise_for_status()
    service_accounts = response.json().get('serviceAccounts', [])

    # Check if the service account already exists
    for sa in service_accounts:
        if sa['name'] == service_account_name:
            logger.info(f"Service account '{service_account_name}' already exists.")
            return sa  # Return the existing service account

    # Create a new service account if it does not exist
    payload = {"name": service_account_name, "role": role}
    response = requests.post(f'{grafana_url}/api/serviceaccounts', auth=auth, headers=headers, json=payload)
    response.raise_for_status()
    logger.info(f"Service account '{service_account_name}' created.")
    return {**response.json(), "created": True}  # Indicate the service account was newly created


    # Check if the service account already exists
    for sa in service_accounts:
        if sa['name'] == service_account_name:
            logger.info(f"Service account '{service_account_name}' already exists.")
            return sa  # Return the existing service account

    # Create a new service account if it does not exist
    payload = {"name": service_account_name, "role": role}
    response = requests.post(f'{grafana_url}/api/serviceaccounts', auth=auth, headers=headers, json=payload)
    response.raise_for_status()
    logger.info(f"Service account '{service_account_name}' created.")
    return response.json()


def create_service_account_token(grafana_url, grafana_username, grafana_password, service_account_id, token_name):
    """Create a token for a specific Grafana service account."""
    auth = (grafana_username, grafana_password)
    headers = {'Content-Type': 'application/json'}
    payload = {"name": token_name}
    response = requests.post(f'{grafana_url}/api/serviceaccounts/{service_account_id}/tokens', auth=auth, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def ensure_grafana_token(namespace, grafana_url, grafana_username, grafana_password, service_account_name, token_name, secret_name):
    """Ensure a Grafana service account token exists and store/update it in a Kubernetes secret."""
    try:
        # Load Kubernetes configuration
        config.load_incluster_config()
        v1 = client.CoreV1Api()

        # Retry logic for connecting to Grafana
        retries = 5
        for attempt in range(retries):
            try:
                logger.info(f"Attempting to connect to Grafana API (Attempt {attempt + 1}/{retries}) at {grafana_url}")
                # Check if the service account exists or create it
                service_account = create_service_account(grafana_url, grafana_username, grafana_password, service_account_name)
                break
            except requests.ConnectionError as e:
                logger.warning(f"Connection to Grafana failed: {e}. Retrying in 10 seconds...")
                time.sleep(10)
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    logger.error(f"Grafana API endpoint not found. URL: {grafana_url}. Check your Grafana version or API URL.")
                    return
                else:
                    raise
        else:
            logger.error("Failed to connect to Grafana after multiple attempts.")
            return

        # If the service account already exists, skip token and secret updates
        if "created" not in service_account:
            logger.info(f"Service account '{service_account_name}' already exists. Skipping token and secret updates.")
            return

        # Create the service account token
        token = create_service_account_token(grafana_url, grafana_username, grafana_password, service_account['id'], token_name)

        # Encode token for Kubernetes secret
        encoded_token = base64.b64encode(token['key'].encode('utf-8')).decode('utf-8')

        # Create or update the Kubernetes secret
        secret_data = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": secret_name},
            "type": "Opaque",
            "data": {"token": encoded_token}
        }
        try:
            v1.create_namespaced_secret(namespace=namespace, body=secret_data)
            logger.info(f"Secret '{secret_name}' created in namespace '{namespace}'.")
        except ApiException as e:
            if e.status == 409:
                v1.patch_namespaced_secret(name=secret_name, namespace=namespace, body=secret_data)
                logger.info(f"Secret '{secret_name}' updated in namespace '{namespace}'.")
            else:
                raise
    except Exception as e:
        logger.error(f"Error in ensure_grafana_token: {e}")


def main():
    namespace = os.getenv('K8S_NAMESPACE', 'default')
    grafana_url = os.getenv('GRAFANA_URL', 'http://grafana:3000')
    grafana_username = os.getenv('GRAFANA_USERNAME')
    grafana_password = os.getenv('GRAFANA_PASSWORD')
    grafana_password_file = os.getenv('GRAFANA_PASSWORD_FILE')  # e.g. /etc/grafana-permission-sidecar/grafana-admin-password
    service_account_name = os.getenv('SERVICE_ACCOUNT_NAME', 'Provisioned-SA')
    token_name = os.getenv('TOKEN_NAME', 'my-grafana-token')
    secret_name = os.getenv('TOKEN_SECRET_NAME', 'my-grafana-token-secret')
    check_interval = int(os.getenv('CHECK_INTERVAL_IN_S', '60'))

    # Read the password from the file if it is not provided directly
    if not grafana_password and grafana_password_file:
        try:
            with open(grafana_password_file, "r") as file:
                grafana_password = file.read().strip()
        except Exception as e:
            logger.error(f"Failed to read Grafana password from file: {e}")

    if not grafana_password:
        logger.error("Grafana password is not provided.")
        return

    while True:
        logger.info("Starting token check/creation cycle.")
        ensure_grafana_token(namespace, grafana_url, grafana_username, grafana_password, service_account_name, token_name, secret_name)
        logger.info(f"Sleeping for {check_interval} seconds.")
        time.sleep(check_interval)

if __name__ == "__main__":
    main()
