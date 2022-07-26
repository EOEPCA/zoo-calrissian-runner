from abc import ABC, abstractmethod


class ExecutionHandler(ABC):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.job_id = None

    def set_job_id(self, job_id):
        self.job_id = job_id

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
    def handle_outputs(self, execution_log, output, usage_report):
        pass

    @abstractmethod
    def get_additional_parameters(self):
        pass
