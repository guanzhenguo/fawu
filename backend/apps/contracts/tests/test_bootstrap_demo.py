import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class BootstrapDemoTests(TestCase):
    @patch.dict(os.environ, {"FAWU_BOOTSTRAP_PASSWORD": "admin123"})
    def test_short_demo_password_requires_explicit_opt_in(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_demo", stdout=StringIO())

        call_command(
            "bootstrap_demo",
            "--allow-insecure-password",
            stdout=StringIO(),
        )

        self.assertIsNotNone(authenticate(username="admin", password="admin123"))
