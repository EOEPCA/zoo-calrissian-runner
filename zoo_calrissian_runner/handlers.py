"""Execution Handler for Calrissian/Kubernetes.

Extends CommonExecutionHandler with Calrissian-specific methods.
"""

import os
from zoo_template_common import CommonExecutionHandler


class ExecutionHandler(CommonExecutionHandler):
    """Extended ExecutionHandler with Calrissian-specific methods.

    Inherits from CommonExecutionHandler to provide STAC catalog processing
    and adds Calrissian/Kubernetes-specific functionality.
    """

    def __init__(self, **kwargs):
        # CommonExecutionHandler expects conf and outputs
        conf = kwargs.get('conf', {})
        outputs = kwargs.get('outputs', {})
        super().__init__(conf, outputs)
        self.__dict__.update(kwargs)
        self.job_id = None

    def set_job_id(self, job_id):
        """Set the job ID for the execution."""
        self.job_id = job_id

    def get_namespace(self):
        """Get the namespace for the execution."""
        return os.environ.get("USE_NAMESPACE", None)

    def get_service_account(self):
        """Get the service account for the execution."""
        return os.environ.get("USE_SERVICE_ACCOUNT", None)

    def get_additional_parameters(self) -> dict[str, str]:
        """Get additional parameters with eoap storage platform."""
        additional_parameters = super().get_additional_parameters()
        additional_parameters["storage_platform"] = "eoap"
        return additional_parameters


__all__ = ['ExecutionHandler']
