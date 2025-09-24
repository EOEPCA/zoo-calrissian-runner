import inspect
import os
import sys
import uuid
from datetime import datetime
from typing import Union

import attr
import cwl_utils
from eoap_cwlwrap import wrap
#from eoap_cwlwrap import wrap_locations
from cwl_loader import dump_cwl
from cwl_loader import load_cwl_from_location as load_workflow
from cwl_loader import load_cwl_from_yaml as load_cwl
from cwl_utils.parser import save
from loguru import logger
from pycalrissian.context import CalrissianContext
from pycalrissian.execution import CalrissianExecution
from pycalrissian.job import CalrissianJob
from pycalrissian.utils import copy_to_volume
import cwl_utils.__meta__ as cwl_meta
import pathlib
import json
import yaml
from io import StringIO
from zoo_calrissian_runner.handlers import ExecutionHandler

# useful class for hints in CWL
@attr.s
class ResourceRequirement:
    coresMin = attr.ib(default=None)
    coresMax = attr.ib(default=None)
    ramMin = attr.ib(default=None)
    ramMax = attr.ib(default=None)
    tmpdirMin = attr.ib(default=None)
    tmpdirMax = attr.ib(default=None)
    outdirMin = attr.ib(default=None)
    outdirMax = attr.ib(default=None)

    @classmethod
    def from_dict(cls, env):
        return cls(**{k: v for k, v in env.items() if k in inspect.signature(cls).parameters})


try:
    import zoo
except ImportError:

    class ZooStub(object):
        def __init__(self):
            self.SERVICE_SUCCEEDED = 3
            self.SERVICE_FAILED = 4

        def update_status(self, conf, progress):
            print(f"Status {progress}")

        def _(self, message):
            print(f"invoked _ with {message}")

    zoo = ZooStub()


class Workflow:
    def __init__(self, cwl, workflow_id):
        self.raw_cwl = cwl
        self.cwl = load_cwl(cwl)
        self.workflow_id = workflow_id

    def get_workflow(self) -> cwl_utils.parser.cwl_v1_0.Workflow:
        # returns a cwl_utils.parser.cwl_v1_0.Workflow)
        ids = [elem.id.split("#")[-1] for elem in self.cwl]

        return self.cwl[ids.index(self.workflow_id)]

    def get_object_by_id(self, id):
        ids = [elem.id.split("#")[-1] for elem in self.cwl]
        return self.cwl[ids.index(id)]

    def get_workflow_inputs(self, mandatory=False):
        inputs = []
        for inp in self.get_workflow().inputs:
            my_current_type = inp.type if cwl_meta.__version__ < "0.16" else inp.type_
            if mandatory:
                if inp.default is not None or my_current_type == ["null", "string"]:
                    continue
                else:
                    inputs.append(inp.id.split("/")[-1])
            else:
                inputs.append(inp.id.split("/")[-1])
        return inputs

    @staticmethod
    def has_scatter_requirement(workflow):
        return any(
            isinstance(
                requirement,
                (
                    cwl_utils.parser.cwl_v1_0.ScatterFeatureRequirement,
                    cwl_utils.parser.cwl_v1_1.ScatterFeatureRequirement,
                    cwl_utils.parser.cwl_v1_2.ScatterFeatureRequirement,
                ),
            )
            for requirement in workflow.requirements
        )

    @staticmethod
    def get_resource_requirement(elem):
        """Gets the ResourceRequirement out of a CommandLineTool or Workflow

        Args:
            elem (CommandLineTool or Workflow): CommandLineTool or Workflow

        Returns:
            cwl_utils.parser.cwl_v1_2.ResourceRequirement or ResourceRequirement
        """
        resource_requirement = []
        
        # look for requirements
        if elem.requirements is not None:
            resource_requirement = [
                requirement
                for requirement in elem.requirements
                if isinstance(
                    requirement,
                    (
                        cwl_utils.parser.cwl_v1_0.ResourceRequirement,
                        cwl_utils.parser.cwl_v1_1.ResourceRequirement,
                        cwl_utils.parser.cwl_v1_2.ResourceRequirement,
                    ),
                )
            ]

            if len(resource_requirement) == 1:
                return resource_requirement[0]

        # look for hints
        if elem.hints is not None:
            resource_requirement = [
                ResourceRequirement.from_dict(hint)
                for hint in elem.hints
                if hint["class"] == "ResourceRequirement"
            ]

            if len(resource_requirement) == 1:
                return resource_requirement[0]

    def eval_resource(self):
        resources = {
            "coresMin": [],
            "coresMax": [],
            "ramMin": [],
            "ramMax": [],
            "tmpdirMin": [],
            "tmpdirMax": [],
            "outdirMin": [],
            "outdirMax": [],
        }

        for elem in self.cwl:
            if isinstance(
                elem,
                (
                    cwl_utils.parser.cwl_v1_0.Workflow,
                    cwl_utils.parser.cwl_v1_1.Workflow,
                    cwl_utils.parser.cwl_v1_2.Workflow,
                ),
            ):
                if resource_requirement := self.get_resource_requirement(elem):
                    for resource_type in [
                        "coresMin",
                        "coresMax",
                        "ramMin",
                        "ramMax",
                        "tmpdirMin",
                        "tmpdirMax",
                        "outdirMin",
                        "outdirMax",
                    ]:
                        if getattr(resource_requirement, resource_type):
                            resources[resource_type].append(getattr(resource_requirement, resource_type))
                for step in elem.steps:
                    if resource_requirement := self.get_resource_requirement(
                        self.get_object_by_id(step.run[1:])
                    ):
                        multiplier = int(os.getenv("SCATTER_MULTIPLIER", 2)) if step.scatter else 1
                        for resource_type in [
                            "coresMin",
                            "coresMax",
                            "ramMin",
                            "ramMax",
                            "tmpdirMin",
                            "tmpdirMax",
                            "outdirMin",
                            "outdirMax",
                        ]:
                            if getattr(resource_requirement, resource_type):
                                resources[resource_type].append(
                                    getattr(resource_requirement, resource_type) * multiplier
                                )
        return resources


class ZooConf:
    def __init__(self, conf):
        self.conf = conf
        self.workflow_id = self.conf["lenv"]["Identifier"]


class ZooInputs:
    def __init__(self, inputs):
        # this conversion is necessary
        # because zoo converts array of length 1 to a string
        if inputs is None:
            self.inputs = {}
            return

        for inp in inputs:
            if (
                "maxOccurs" in inputs[inp].keys()
                and int(inputs[inp]["maxOccurs"]) > 1
                and not isinstance(inputs[inp]["value"], list)
            ):
                inputs[inp]["value"] = [inputs[inp]["value"]]

        self.inputs = inputs

    def get_input_value(self, key):
        try:
            return self.inputs[key]["value"]
        except KeyError as exc:
            raise exc
        except TypeError:
            pass

    def get_processing_parameters(self):
        """Returns a list with the input parameters keys"""
        res={}
        hasVal=False;
        for key, value in self.inputs.items():
            logger.info(f"Processing input {key} with value {value}")
            if "format" in value:
                # We can also use res[key]=value
                # TBD: Should we distinguish between file and basic strings with format, such as date, datetime?
                # TBD: Should we find the corresponding class from the schema definition?
                res[key]={
                    "format": value["format"],
                    "value": value["value"],
                }
            elif "dataType" in value:
                if isinstance(value["dataType"],list):
                    # How should we pass array for an input?
                    res[key]=value["value"]
                else:
                    if value["value"]=="NULL":
                        res[key]=None
                    else:
                        if value["dataType"] in ["double","float"]:
                            res[key]=float(value["value"])
                        elif value["dataType"] == "integer":
                            res[key]=int(value["value"])
                        elif value["dataType"] == "boolean":
                            res[key]=bool(value["value"])
                        else:
                            res[key]=value["value"]
            else:
                # default case
                if "cache_file" in value:
                    if "isArray" in value and value["isArray"]=="true":
                        res[key]=[]
                        for i in range(len(value["value"])):
                            if "mimeType" in value:
                                res[key].append({
                                    "format": value["mimeType"][i],
                                    "value": value["value"][i],
                                })
                            else:
                                res[key].append({
                                    "format": "text/plain",
                                    "value": value["value"][i],
                                })
                    else:
                        if "mimeType" in value:
                            res[key]={
                                "format": value["mimeType"],
                                "value": value["value"]
                            }
                        else:
                            res[key]={
                                "format": "text/plain",
                                "value": value["value"]
                            }
                else:
                    if "lowerCorner" in value and "upperCorner" in value:
                        res[key]={
                            "format": "ogc-bbox",
                            "bbox": json.loads(value["value"]),
                            "crs": value["crs"].replace("http://www.opengis.net/def/crs/OGC/1.3/","")
                        }
                    else:
                        res[key]=value["value"]
        return res 


class ZooOutputs:
    def __init__(self, outputs):
        self.outputs = outputs
        # decuce the output key
        output_keys = list(self.outputs.keys())
        if len(output_keys) > 0:
            self.output_key = output_keys[0]
        else:
            self.output_key = "stac"
            if "stac" not in self.outputs.keys():
                self.outputs["stac"] = {}

    def get_output_parameters(self):
        """Returns a list with the output parameters keys"""
        return {key: value["value"] for key, value in self.outputs.items()}

    def set_output(self, value):
        """set the output result value"""
        self.outputs[self.output_key]["value"] = value


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
        self.workflow = Workflow(cwl, self.zoo_conf.workflow_id)

        self.handler = execution_handler

        self.storage_class = os.environ.get("STORAGE_CLASS", "openebs-nfs-test")
        if self.handler is not None:
            self.dedicated_namespace = self.handler.get_namespace()
        else:
            self.dedicated_namespace = None
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

        resources = self.workflow.eval_resource()

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
        resources = self.workflow.eval_resource()

        max_cores = max(max(resources["coresMin"] or [0]), max(resources["coresMax"] or [0]))

        if max_cores == 0:
            max_cores = int(os.environ.get("DEFAULT_MAX_CORES"))
        logger.info(f"max cores: {max_cores}")

        return max_cores

    def get_max_ram(self) -> str:
        """returns the maximum RAM that pods can use"""
        resources = self.workflow.eval_resource()
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
        return self.workflow.get_workflow_inputs(mandatory=mandatory)

    def assert_parameters(self):
        """checks all mandatory processing parameters were provided"""
        return all(
            elem in list(self.get_processing_parameters().keys())
            for elem in self.get_workflow_inputs(mandatory=True)
        )

    def get_annotations(self):
        """Get the labels for the execution."""
        return self.zoo_conf.conf["pod_annotations"] if "pod_annotations" in self.zoo_conf.conf else None

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
                annotations=self.get_annotations(),
            )
        else:
            session = CalrissianContext.from_existing_namespace(
                namespace=namespace,
                storage_class=self.storage_class,
                volume_size=self.get_volume_size(),
                image_pull_secrets=secret_config,
                annotations=self.get_annotations(),
                service_account=self.handler.get_service_account(),
            )
        session.initialise()
        self.update_status(progress=15, message="processing environment created, preparing execution")

        processing_parameters = {
            "process": namespace,
            **self.get_processing_parameters(),
            **self.handler.get_additional_parameters(),
        }


        logger.info(f"Processing parameters: {processing_parameters}")

        # Upload input complex data into calrissian_wdir
        for i in processing_parameters:
            if isinstance(processing_parameters[i],dict):
                if processing_parameters[i].get("class",None)=="File":
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

        logger.info("create Calrissian job")
        self.update_status(progress=21, message="Submit execution")
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

        # Load the directory stage-in CWL
        directory_stage_in_cwl = None
        if os.environ.get("WRAPPER_STAGE_IN", None) is not None:
            directory_stage_in_cwl = load_workflow(os.environ.get("WRAPPER_STAGE_IN", "/assets/stagein.yaml"))

        # Load the directory stage-in CWL
        file_stage_in_cwl = load_workflow(os.environ.get("WRAPPER_STAGE_IN1", "/assets/stagein-file.yaml"))

        # Load the directory stage-out CWL
        try:
            directory_stage_out_cwl = load_workflow(os.environ.get("WRAPPER_STAGE_OUT", "/assets/stageout.yaml"))
        except Exception as e:
            logger.error(f"Cannot load stage-out CWL: {e}")
            directory_stage_out_cwl = None

        try:
            wrapped_workflow = wrap(
                workflows=self.workflow.cwl,
                workflow_id=workflow_id,
                directory_stage_in=directory_stage_in_cwl,
                file_stage_in=file_stage_in_cwl,
                stage_out=directory_stage_out_cwl,
            )
            # TODO: this is a workaround, remove it as soon as a better solution is available
            buffer = StringIO()
            dump_cwl(
                process=wrapped_workflow,
                stream=buffer
            )
            wf = yaml.safe_load(buffer.getvalue())
        except Exception as e:
            logger.error(f"Cannot wrap CWL: {e}")
            raise e

        return wf
