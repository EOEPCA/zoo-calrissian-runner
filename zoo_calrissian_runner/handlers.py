from abc import ABC, abstractmethod
import os

class ExecutionHandler(ABC):
    def __init__(self, **kwargs):
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

    @abstractmethod
    def pre_execution_hook(self, **kwargs):
        pass

    @abstractmethod
    def post_execution_hook(self, **kwargs):
        pass

    @abstractmethod
    def get_secrets(self):
        pass

    @abstractmethod
    def get_pod_env_vars(self):
        pass

    @abstractmethod
    def get_pod_node_selector(self):
        pass

    @abstractmethod
    def handle_outputs(self, execution_log, output, usage_report, tool_logs=None):
        pass

    @abstractmethod
    def get_additional_parameters(self):
        pass
