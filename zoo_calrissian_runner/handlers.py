"""Execution Handler for Calrissian/Kubernetes.

Re-exports ExecutionHandler from zoo-runner-common with additional methods.
"""

import os
# import sys

# Add zoo-runner-common to path
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../zoo-runner-common')))
from handlers import ExecutionHandler as BaseExecutionHandler


class ExecutionHandler(BaseExecutionHandler):
    """Extended ExecutionHandler with Calrissian-specific methods."""

    def __init__(self, **kwargs):
        super().__init__()
        self.__dict__.update(kwargs)
        self.job_id = None

    def set_job_id(self, job_id):
        self.job_id = job_id

    def get_namespace(self):
        """Get the namespace for the execution."""
        return os.environ.get("USE_NAMESPACE", None)

    def get_service_account(self):
        """Get the service account for the execution."""
        return os.environ.get("USE_SERVICE_ACCOUNT", None)


__all__ = ['ExecutionHandler']
