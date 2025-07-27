import inspect
import os
import sys
import uuid
from datetime import datetime
from typing import Union

import attr
import cwl_utils
from cwl_utils.parser import load_document_by_yaml
from cwl_wrapper.parser import Parser
from loguru import logger
from pycalrissian.context import CalrissianContext
from pycalrissian.execution import CalrissianExecution
from pycalrissian.job import CalrissianJob
from pycalrissian.utils import copy_to_volume

#import sys
#print("PYTHONPATH at runtime:", sys.path)


#from zoo_calrissian_runner.handlers import ExecutionHandler



sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../zoo-runner-common')))
from base_handler import ExecutionHandler
from zoostub import ZooStub
zoo = ZooStub()

from zoo_conf import ZooConf, ZooInputs, ZooOutputs, CWLWorkflow

from base_runner import BaseRunner


class ZooCalrissianRunner:
    def __init__(
        self,
        cwl,
        conf,
        inputs,
        outputs,
        execution_handler: Union[ExecutionHandler, None] = None,
    ):
        self.zoo_conf = ZooConf(conf)
        self.inputs = ZooInputs(inputs)
        self.outputs = ZooOutputs(outputs)
        self.cwl = CWLWorkflow(cwl, self.zoo_conf.workflow_id)

        self.handler = execution_handler

        self.storage_class = os.environ.get("STORAGE_CLASS", "openebs-nfs-test")
        self.dedicated_namespace = os.environ.get("USE_NAMESPACE", None)
        self.monitor_interval = 30
        if "lenv" in self.zoo_conf.conf and "usid" in self.zoo_conf.conf["lenv"]:
            if self.dedicated_namespace is None:
                uuidString=self.zoo_conf.conf['lenv']['usid']
                self._namespace_name = ZooCalrissianRunner.shorten_namespace(
                    f"{str(self.zoo_conf.workflow_id).replace('_', '-')}-"
                    f"{uuidString}"
                )
            else:
                self._namespace_name = self.shorten_namespace(
                    self.dedicated_namespace
                )
        else:
            self._namespace_name = None

    @staticmethod
    def shorten_namespace(value: str) -> str:
        """shortens the namespace to 63 characters"""
        while len(value) > 63:
            value = value[:-1]
            while value.endswith("-"):
                value = value[:-1]
        return value

    def get_volume_size(self) -> str:
        """returns volume size that the pods share"""

        resources = self.cwl.eval_resource()

        # TODO how to determine the "right" volume size
        volume_size = max(max(resources["tmpdirMin"] or [0]), max(resources["tmpdirMax"] or [0])) + max(
            max(resources["outdirMin"] or [0]), max(resources["outdirMax"] or [0])
        )

        if volume_size == 0:
            volume_size = os.environ.get("DEFAULT_VOLUME_SIZE")

        logger.info(f"volume_size: {volume_size}Mi")

        return f"{volume_size}Mi"

    def get_max_cores(self) -> int:
        """returns the maximum number of cores that pods can use"""
        resources = self.cwl.eval_resource()

        max_cores = max(max(resources["coresMin"] or [0]), max(resources["coresMax"] or [0]))

        if max_cores == 0:
            max_cores = int(os.environ.get("DEFAULT_MAX_CORES"))
        logger.info(f"max cores: {max_cores}")

        return max_cores

    def get_max_ram(self) -> str:
        """returns the maximum RAM that pods can use"""
        resources = self.cwl.eval_resource()
        max_ram = max(max(resources["ramMin"] or [0]), max(resources["ramMax"] or [0]))

        if max_ram == 0:
            max_ram = int(os.environ.get("DEFAULT_MAX_RAM"))
        logger.info(f"max RAM: {max_ram}Mi")

        return f"{max_ram}Mi"

    def get_namespace_name(self):
        """creates or returns the namespace"""
        if self._namespace_name is None:
            return self.shorten_namespace(
                f"{str(self.zoo_conf.workflow_id).replace('_', '-')}-"
                f"{str(datetime.now().timestamp()).replace('.', '')}-{uuid.uuid4()}"
            )
        else:
            return self._namespace_name

    def update_status(self, progress: int, message: str = None) -> None:
        """updates the execution progress (%) and provides an optional message"""
        if message:
            self.zoo_conf.conf["lenv"]["message"] = message

        zoo.update_status(self.zoo_conf.conf, progress)

    def get_workflow_id(self):
        """returns the workflow id (CWL entry point)"""
        return self.zoo_conf.workflow_id

    def get_processing_parameters(self):
        """Gets the processing parameters from the zoo inputs"""
        return self.inputs.get_processing_parameters()

    def get_workflow_inputs(self, mandatory=False):
        """Returns the CWL workflow inputs"""
        return self.cwl.get_workflow_inputs(mandatory=mandatory)

    def assert_parameters(self):
        """checks all mandatory processing parameters were provided"""
        return all(
            elem in list(self.get_processing_parameters().keys())
            for elem in self.get_workflow_inputs(mandatory=True)
        )

    def execute(self, wall_time=None):
        self.update_status(progress=2, message="Pre-execution hook")
        self.handler.pre_execution_hook()

        if not (self.assert_parameters()):
            logger.error("Mandatory parameters missing")
            return zoo.SERVICE_FAILED

        logger.info("execution started")
        self.update_status(progress=5, message="starting execution")

        logger.info("wrap CWL workflow with stage-in/out steps")
        wrapped_workflow = self.wrap()
        self.update_status(progress=10, message="workflow wrapped, creating processing environment")

        logger.info("create kubernetes namespace for Calrissian execution")

        # TODO how do we manage the secrets
        secret_config = self.handler.get_secrets()

        namespace = self.get_namespace_name()

        self.handler.set_job_id(job_id=namespace)

        logger.info(f"namespace: {namespace}")

        if self.dedicated_namespace is None:
            session = CalrissianContext(
                namespace=namespace,
                storage_class=self.storage_class,
                volume_size=self.get_volume_size(),
                image_pull_secrets=secret_config,
            )
        else:
            session = CalrissianContext.from_existing_namespace(
                namespace=namespace,
                storage_class=self.storage_class,
                volume_size=self.get_volume_size(),
                image_pull_secrets=secret_config,
                service_account=os.environ.get("USE_SERVICE_ACCOUNT", None),
            )
        session.initialise()
        self.update_status(progress=15, message="processing environment created, preparing execution")

        processing_parameters = {
            "process": namespace,
            **self.get_processing_parameters(),
            **self.handler.get_additional_parameters(),
        }


        self.update_status(progress=20, message="upload required files")


        # Upload input complex data into calrissian_wdir
        for i in processing_parameters:
            if isinstance(processing_parameters[i],dict):
                if processing_parameters[i]["class"]=="File":
                    copy_to_volume(
                        context=session,
                        volume={
                            "name": session.calrissian_wdir,
                            "persistentVolumeClaim": {
                                "claimName": session.calrissian_wdir
                            }
                        },
                        volume_mount={
                            "name": session.calrissian_wdir,
                            "mountPath": "/calrissian",
                        },
                        source_paths=[
                            processing_parameters[i]["path"]
                        ],
                        destination_path="/calrissian",
                    )
                    processing_parameters[i]["path"]=processing_parameters[i]["path"].replace(self.zoo_conf.conf["main"]["tmpPath"],"/calrissian")
        # checks if all parameters where provided

        logger.info("create Calrissian job")
        job = CalrissianJob(
            cwl=wrapped_workflow,
            params=processing_parameters,
            runtime_context=session,
            cwl_entry_point="main",
            max_cores=self.get_max_cores(),
            max_ram=self.get_max_ram(),
            pod_env_vars=self.handler.get_pod_env_vars(),
            pod_node_selector=self.handler.get_pod_node_selector(),
            debug=True,
            no_read_only=True,
            tool_logs=True,
        )

        self.update_status(progress=23, message="execution submitted")

        logger.info("execution")
        self.execution = CalrissianExecution(job=job, runtime_context=session)
        self.execution.submit()

        self.execution.monitor(interval=self.monitor_interval, wall_time=wall_time)

        if self.execution.is_complete():
            logger.info("execution complete")

        if self.execution.is_succeeded():
            exit_value = zoo.SERVICE_SUCCEEDED
        else:
            exit_value = zoo.SERVICE_FAILED

        self.update_status(progress=90, message="delivering outputs, logs and usage report")

        logger.info("handle outputs execution logs")
        output = self.execution.get_output()
        log = self.execution.get_log()
        usage_report = self.execution.get_usage_report()
        tool_logs = self.execution.get_tool_logs()

        self.outputs.set_output(output)

        self.handler.handle_outputs(
            log=log,
            output=output,
            usage_report=usage_report,
            tool_logs=tool_logs,
        )

        self.update_status(progress=97, message="Post-execution hook")
        self.handler.post_execution_hook(
            log=log,
            output=output,
            usage_report=usage_report,
            tool_logs=tool_logs,
        )

        self.update_status(progress=99, message="clean-up processing resources")

        # use an environment variable to decide if we want to clean up the resources
        if os.environ.get("KEEP_SESSION", "false") == "false":
            logger.info("clean-up kubernetes resources")
            session.dispose()
        else:
            logger.info("kubernetes resources not cleaned up")

        self.update_status(
            progress=100,
            message=f'execution {"failed" if exit_value == zoo.SERVICE_FAILED else "successful"}',
        )

        return exit_value

    def wrap(self):
        workflow_id = self.get_workflow_id()

        wf = Parser(
            cwl=self.cwl.raw_cwl,
            output=None,
            stagein=os.environ.get("WRAPPER_STAGE_IN", "assets/stagein.yaml"),
            stageout=os.environ.get("WRAPPER_STAGE_OUT", "assets/stageout.yaml"),
            maincwl=os.environ.get("WRAPPER_MAIN", "assets/maincwl.yaml"),
            rulez=os.environ.get("WRAPPER_RULES", "assets/rules.yaml"),
            assets=None,
            workflow_id=workflow_id,
        )

        return wf.out
