import requests
import logging

class ForgejoClient:
    def __init__(self, api_url, token):
        """
        Initialize the Forgejo client.
        :param api_url: Base URL for the API (e.g., https://git.anagora.org/api/v1)
        :param token: Access token for authentication
        """
        self.api_url = api_url.rstrip('/')
        self.headers = {
            'Authorization': f'token {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self.logger = logging.getLogger(__name__)

    def create_user(self, username, email, password, must_change_password=False):
        """
        Create a new user.
        Requires admin privileges.
        """
        endpoint = f"{self.api_url}/admin/users"
        payload = {
            "username": username,
            "email": email,
            "password": password,
            "must_change_password": must_change_password,
            "send_notify": False, # Don't rely on email sending working immediately
            "login_name": username,
            "source_id": 0 # Local
        }
        
        response = requests.post(endpoint, json=payload, headers=self.headers)
        if response.status_code == 201:
            self.logger.info(f"Successfully created user {username}")
            return response.json()
        else:
            self.logger.error(f"Failed to create user {username}: {response.text}")
            response.raise_for_status()

    def create_repo(self, username, repo_name, description="", private=False, auto_init=True):
        """
        Create a repository for a specific user.
        Requires admin privileges (to act on behalf of the user).
        """
        # Endpoint for admin to create a repo for a user
        endpoint = f"{self.api_url}/admin/users/{username}/repos"
        payload = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": auto_init, # Initialize with README so it's valid immediately
            "default_branch": "main"
        }

        response = requests.post(endpoint, json=payload, headers=self.headers)
        if response.status_code == 201:
            self.logger.info(f"Successfully created repo {username}/{repo_name}")
            return response.json()
        else:
            self.logger.error(f"Failed to create repo {username}/{repo_name}: {response.text}")
            response.raise_for_status()

    def add_deploy_key(self, username, repo_name, title, key, read_only=False):
        """
        Add a deploy key to a repository.
        """
        endpoint = f"{self.api_url}/repos/{username}/{repo_name}/keys"
        payload = {
            "title": title,
            "key": key,
            "read_only": read_only
        }

        response = requests.post(endpoint, json=payload, headers=self.headers)
        if response.status_code == 201:
            self.logger.info(f"Successfully added deploy key '{title}' to {username}/{repo_name}")
            return response.json()
        else:
            self.logger.error(f"Failed to add deploy key to {username}/{repo_name}: {response.text}")
            # Don't raise immediately, just return None/False so the caller can decide
            return None

    def check_user_exists(self, username):
        """
        Check if a user exists.
        """
        endpoint = f"{self.api_url}/users/{username}"
        response = requests.get(endpoint, headers=self.headers)
        return response.status_code == 200
