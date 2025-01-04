import base64
import json
import os
import tempfile
import unittest

import yaml
from dotenv import load_dotenv

from zoo_calrissian_runner import ZooCalrissianRunner
from zoo_calrissian_runner.handlers import ExecutionHandler

load_dotenv()


class TestRunnerResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_output_file = tempfile.NamedTemporaryFile()

        try:
            import zoo
        except ImportError:
            print("Not running in zoo instance")

            class ZooStub(object):
                def __init__(self):
                    self.SERVICE_SUCCEEDED = 3
                    self.SERVICE_FAILED = 4

                def update_status(self, conf, progress):
                    print(f"Status {progress}")

                def _(self, message):
                    print(f"invoked _ with {message}")

            zoo = ZooStub()

        cls.zoo = zoo

        conf = {}
        conf["lenv"] = {"message": ""}
        conf["lenv"] = {"Identifier": "burned-area"}
        conf["tmpPath"] = "/tmp"

        cls.conf = conf

        with open(
            os.path.join("tests", "app-packages", "app-package-1.cwl"),
            "r",
        ) as stream:
            cls.cwl_1 = yaml.safe_load(stream)

        with open(
            os.path.join("tests", "app-packages", "app-package-4.cwl"),
            "r",
        ) as stream:
            cls.cwl_4 = yaml.safe_load(stream)

        class CalrissianRunnerExecutionHandler(ExecutionHandler):
            def pre_execution_hook(self):
                # Add logic here for actions before execution, if needed
                pass

            def post_execution_hook(self):
                # Add logic here for actions after execution, if needed
                pass
            
            def get_pod_env_vars(self):
                # sets two env vars in the pod launched by Calrissian
                return {"A": "1", "B": "1"}

            def get_pod_node_selector(self):
                return None

            def get_secrets(self):
                username = os.environ["CR_USERNAME"]
                password = os.environ["CR_TOKEN"]
                email = os.environ["CR_EMAIL"]
                registry = os.environ["CR_ENDPOINT"]

                auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")

                secret_config = {
                    "auths": {
                        registry: {
                            "username": username,
                            "password": password,
                            "email": email,
                            "auth": auth,
                        },
                        "registry.gitlab.com": {"auth": ""},  # noqa: E501
                    }
                }

                return secret_config

            def get_additional_parameters(self):
                endpoint = os.environ["AWS_SERVICE_URL"]
                region = os.environ["AWS_REGION"]
                access_key = os.environ["AWS_ACCESS_KEY_ID"]
                secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]

                return {
                    "ADES_STAGEOUT_AWS_SERVICEURL": endpoint,
                    "ADES_STAGEOUT_AWS_REGION": region,
                    "ADES_STAGEOUT_AWS_ACCESS_KEY_ID": access_key,
                    "ADES_STAGEOUT_AWS_SECRET_ACCESS_KEY": secret_key,
                    "ADES_STAGEIN_AWS_SERVICEURL": endpoint,
                    "ADES_STAGEIN_AWS_REGION": region,
                    "ADES_STAGEIN_AWS_ACCESS_KEY_ID": access_key,
                    "ADES_STAGEIN_AWS_SECRET_ACCESS_KEY": secret_key,
                    "ADES_STAGEOUT_OUTPUT": "s3://eoepca-ades",
                }

            def handle_outputs(self, log, output, usage_report):
                os.makedirs(
                    os.path.join(self.conf["tmpPath"], self.job_id),
                    mode=0o777,
                    exist_ok=True,
                )
                with open(os.path.join(self.conf["tmpPath"], self.job_id, "job.log"), "w") as f:
                    f.writelines(log)

                with open(
                    os.path.join(self.conf["tmpPath"], self.job_id, "output.json"), "w"
                ) as output_file:
                    json.dump(output, output_file, indent=4)

                with open(
                    os.path.join(self.conf["tmpPath"], self.job_id, "usage-report.json"),
                    "w",
                ) as usage_report_file:
                    json.dump(usage_report, usage_report_file, indent=4)

                outputs = {"Result": {"value": ""}}

                aggregated_outputs = {}
                aggregated_outputs = {
                    "usage_report": usage_report,
                    "outputs": outputs,
                    "log": os.path.join(self.job_id, "job.log"),
                }

                with open(
                    os.path.join(self.conf["tmpPath"], self.job_id, "report.json"), "w"
                ) as report_file:
                    json.dump(aggregated_outputs, report_file, indent=4)

        cls.execution_handler = CalrissianRunnerExecutionHandler

    def test_empty_resource_definition(self):
        inputs = {
            "pre_event": {
                "value": "https://catalog.terradue.com/sentinel2/search?format=atom&uid=S2A_MSIL1C_20220628T112131_N0400_R037_T29SPD_20220628T145901&do=[terradue]"  # noqa: E501
            },
            "post_event": {
                "value": "https://catalog.terradue.com/sentinel2/search?format=atom&uid=S2B_MSIL1C_20220723T112119_N0400_R037_T29SPD_20220723T121256&do=[terradue]"  # noqa: E501
            },
            "ndvi_threshold": {"value": "0.19"},
            "ndwi_threshold": {"value": "0.18"},
        }

        outputs = {"Result": {"value": ""}}

        runner = ZooCalrissianRunner(
            cwl=self.cwl_1,
            conf=self.conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=self.execution_handler(conf=self.conf),
        )
        self.assertEqual(runner.get_max_cores(), int(os.environ["DEFAULT_MAX_CORES"]))
        self.assertEqual(runner.get_max_ram(), os.environ["DEFAULT_MAX_RAM"] + "Mi")

    def test_volume_size(self):
        inputs = {
            "pre_event": {
                "value": "https://catalog.terradue.com/sentinel2/search?format=atom&uid=S2A_MSIL1C_20220628T112131_N0400_R037_T29SPD_20220628T145901&do=[terradue]"  # noqa: E501
            },
            "post_event": {
                "value": "https://catalog.terradue.com/sentinel2/search?format=atom&uid=S2B_MSIL1C_20220723T112119_N0400_R037_T29SPD_20220723T121256&do=[terradue]"  # noqa: E501
            },
            "ndvi_threshold": {"value": "0.19"},
            "ndwi_threshold": {"value": "0.18"},
        }

        outputs = {"Result": {"value": ""}}

        runner = ZooCalrissianRunner(
            cwl=self.cwl_4,
            conf=self.conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=self.execution_handler(conf=self.conf),
        )
        self.assertEqual(runner.get_volume_size(), "20000Mi")
