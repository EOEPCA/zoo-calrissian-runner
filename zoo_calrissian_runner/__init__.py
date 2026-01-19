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

# Import from zoo-runner-common
import os
# Add zoo-runner-common to path (adjust based on installation)
# import sys
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../zoo-runner-common')))
from base_runner import BaseRunner
from zoo_conf import ZooConf, ZooInputs, ZooOutputs, CWLWorkflow
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
    # Use centralized ZooStub from zoo-runner-common package
    from zoostub import ZooStub
    zoo = ZooStub()


# Note: ZooConf, ZooInputs, ZooOutputs, CWLWorkflow are now in zoo-runner-common

class ZooCalrissianRunner(BaseRunner):
    def __init__(
        self,
        cwl,
        conf,
        inputs,
        outputs,
        execution_handler: Union[ExecutionHandler, None] = None,
    ):
        # BaseRunner.__init__ creates: self.conf, self.inputs, self.outputs, self.workflow
        super().__init__(cwl, inputs, conf, outputs, execution_handler)

        # Aliases for backward compatibility
        self.handler = self.execution_handler
        self.zoo_conf = self.conf

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

    # Note: get_volume_size() is now inherited from BaseRunner


    # Note: get_max_cores() is now inherited from BaseRunner


    # Note: get_max_ram() is now inherited from BaseRunner

    def get_namespace_name(self):
        """creates or returns the namespace"""
        if self._namespace_name is None:
            return self.shorten_namespace(
                f"{str(self.zoo_conf.workflow_id).replace('_', '-')}-"
                f"{str(datetime.now().timestamp()).replace('.', '')}-{uuid.uuid4()}"
            )
        else:
            return self._namespace_name


    # Note: update_status() is now inherited from BaseRunner

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

        # Get orchestrator workflow from wrapped workflow to use its input types
        orchestrator_workflow = None
        orchestrator_uri_inputs = set()  # Track which inputs are URI types
        for elem in wrapped_workflow.get('$graph', []):
            if elem.get('id') == 'main' and elem.get('class') == 'Workflow':
                # Convert to a workflow-like object that get_processing_parameters can read
                from types import SimpleNamespace
                orchestrator_workflow = SimpleNamespace(inputs=[])
                for inp in elem.get('inputs', []):
                    inp_obj = SimpleNamespace(
                        id=inp.get('id'),
                        type_=inp.get('type')
                    )
                    orchestrator_workflow.inputs.append(inp_obj)

                    # Track URI type inputs (from string_format.yaml)
                    inp_type = inp.get('type')
                    if isinstance(inp_type, str) and 'string_format.yaml' in inp_type:
                        # Extract short input name (e.g., "main#pre_event" -> "pre_event")
                        inp_name = inp.get('id', '').split('#')[-1] if '#' in inp.get('id', '') else inp.get('id', '')
                        inp_name = inp_name.split('/')[-1]  # Also handle workflow/input format
                        orchestrator_uri_inputs.add(inp_name)
                break

        processing_parameters = {
            "process": namespace,
            **self.inputs.get_processing_parameters(orchestrator_workflow),
            **self.handler.get_additional_parameters(),
        }

        # Transform string values to {value: ...} format for URI type inputs
        for key in orchestrator_uri_inputs:
            if key in processing_parameters and isinstance(processing_parameters[key], str):
                logger.info(f"Converting URI parameter '{key}' to {{value: ...}} format for orchestrator")
                processing_parameters[key] = {"value": processing_parameters[key]}


        # Transform ADES_* parameters to match orchestrator expectations
        # Get orchestrator inputs from wrapped workflow
        orchestrator_inputs = set()
        for elem in wrapped_workflow.get('$graph', []):
            if elem.get('id') == 'main' and elem.get('class') == 'Workflow':
                orchestrator_inputs = {inp['id'] for inp in elem.get('inputs', [])}
                break

        # Remove ADES_ prefix for orchestrator parameters
        transformed_parameters = {}
        for key, value in processing_parameters.items():
            # Check if there's a matching orchestrator input without ADES_ prefix
            if key.startswith('ADES_'):
                unprefixed_key = key.replace('ADES_', '', 1)
                if unprefixed_key in orchestrator_inputs:
                    logger.info(f"Transforming parameter {key} → {unprefixed_key} for orchestrator")
                    transformed_parameters[unprefixed_key] = value
                else:
                    transformed_parameters[key] = value
            else:
                transformed_parameters[key] = value

        processing_parameters = transformed_parameters
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

    def load_a_workflow(self, location):
        try:
            workflow = load_workflow(location)
        except Exception as e:
            logger.error(f"Cannot load CWL from {location}: {e}")
            workflow = None
        return workflow

    def wrap(self):
        workflow_id = self.get_workflow_id()
        
        # Get the workflow object
        workflow = self.workflow.get_workflow()
        
        # Rename any CommandLineTool/process named 'main' to avoid conflict with orchestrator
        # The orchestrator created by eoap-cwlwrap is always named 'main'
        for elem in self.workflow.cwl:
            if hasattr(elem, 'id') and elem.id == 'main':
                # Rename to avoid conflict - use the workflow name or 'clt'
                new_id = f"{workflow_id}_clt"
                logger.info(f"Renaming '{elem.id}' to '{new_id}' to avoid conflict with orchestrator")
                elem.id = new_id
                
                # Update any references to this process in workflow steps
                if hasattr(workflow, 'steps'):
                    for step in workflow.steps:
                        if step.run == '#main':
                            step.run = f'#{new_id}'
                            logger.info(f"Updated step '{step.id}' to reference '#{new_id}'")
        
        # Now wrap the workflow (not the CommandLineTool)
        process_to_wrap = workflow.id
        logger.info(f"Wrapping process: {process_to_wrap}")

        # Load the directory stage-in CWL
        directory_stage_in_cwl = self.load_a_workflow(
            os.environ.get("WRAPPER_STAGE_IN", "/assets/stagein.yaml")
        )

        # Load the directory stage-in CWL
        file_stage_in_cwl = self.load_a_workflow(
            os.environ.get("WRAPPER_STAGE_IN_FILE", "/assets/stagein-file.yaml")
        )

        # Load the directory stage-out CWL
        directory_stage_out_cwl = self.load_a_workflow(
            os.environ.get("WRAPPER_STAGE_OUT", "/assets/stageout.yaml")
        )

        try:
            wrapped_workflow = wrap(
                workflows=self.workflow.cwl,
                workflow_id=process_to_wrap,
                directory_stage_in=directory_stage_in_cwl,
                file_stage_in=file_stage_in_cwl,
                stage_out=directory_stage_out_cwl,
            )
            
            # Serialize using dump_cwl
            from cwl_loader import dump_cwl
            from io import StringIO
            import yaml
            
            stream = StringIO()
            try:
                dump_cwl(wrapped_workflow, stream)
                wf = yaml.safe_load(stream.getvalue())
            except Exception as e:
                # Fallback: manual serialization if dump_cwl fails
                logger.warning(f"dump_cwl failed: {e}, using manual serialization")
                if isinstance(wrapped_workflow, list):
                    wf = {
                        '$graph': [proc.save() for proc in wrapped_workflow],
                        'cwlVersion': 'v1.2'
                    }
                else:
                    wf = wrapped_workflow.save()
                
        except Exception as e:
            logger.error(f"Cannot wrap CWL: {e}")
            raise e

        return wf
