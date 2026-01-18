import base64
import json
import os
import tempfile
import unittest

import yaml

from zoo_calrissian_runner import ZooCalrissianRunner
from zoo_calrissian_runner.handlers import ExecutionHandler
from dotenv import load_dotenv

load_dotenv()


class TestSentinel2Composites(unittest.TestCase):
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
            conf["lenv"] = {"Identifier": "main"}
            conf["tmpPath"] = "/tmp"

            cls.conf = conf

            with open("tests/app-s2-composites.0.1.0.cwl", "r") as stream:
                cwl = yaml.safe_load(stream)

            cls.cwl = cwl
            
    @unittest.skipIf(os.getenv("CI_TEST_SKIP") == "1", "Test is skipped via env variable")
    def test_execution(self):
        class CalrissianRunnerExecutionHandler(ExecutionHandler):
            def pre_execution_hook(self):
                # Add logic here for actions before execution, if needed
                pass

            def post_execution_hook(self, **kwargs):
                # Add logic here for actions after execution, if needed
                pass
            
            def get_pod_env_vars(self):
                # sets two env vars in the pod launched by Calrissian
                return {"A": "1", "B": "1"}

            def get_pod_node_selector(self):
                return None

            def get_secrets(self):
                username = os.getenv("CR_USERNAME", None)
                password = os.getenv("CR_TOKEN", None)
                registry = os.getenv("CR_ENDPOINT", None)

                auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")

                return {
                    "auths": {
                        registry: {
                            "username": username,
                            "auth": auth,
                        },
                    }
                }

            def get_additional_parameters(self):
                return {
                    "ADES_STAGEOUT_AWS_SERVICEURL": os.getenv("AWS_SERVICE_URL", None),
                    "ADES_STAGEOUT_AWS_REGION": os.getenv("AWS_REGION", None),
                    "ADES_STAGEOUT_AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", None),
                    "ADES_STAGEOUT_AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", None),
                    "ADES_STAGEIN_AWS_SERVICEURL": os.getenv("AWS_SERVICE_URL", None),
                    "ADES_STAGEIN_AWS_REGION": os.getenv("AWS_REGION", None),
                    "ADES_STAGEIN_AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", None),
                    "ADES_STAGEIN_AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", None),
                    "ADES_STAGEOUT_OUTPUT": os.getenv("AWS_ACCESS_KEY_ID", None),
                }

            def handle_outputs(self, log, output, usage_report, tool_logs):
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

                aggregated_outputs = {}
                aggregated_outputs = {
                    "usage_report": usage_report,
                    "outputs": output,
                    "log": os.path.join(self.job_id, "job.log"),
                }

                with open(
                    os.path.join(self.conf["tmpPath"], self.job_id, "report.json"), "w"
                ) as report_file:
                    json.dump(aggregated_outputs, report_file, indent=4)

        inputs = {
            "post_stac_item": {
                "value": "https://earth-search.aws.element84.com/v0/collections/sentinel-s2-l2a-cogs/items/S2B_53HPA_20210723_0_L2A"  # noqa: E501
            },  # noqa: E501
            "pre_stac_item": {
                "value": "https://earth-search.aws.element84.com/v0/collections/sentinel-s2-l2a-cogs/items/S2B_53HPA_20210703_0_L2A"  # noqa: E501
            },  # noqa: E501
            "aoi": {"value": "136.659,-35.96,136.923,-35.791"},
        }

        outputs = {"Result": {"value": ""}}
        #os.environ["KUBECONFIG"] = ".kube-config"

        runner = ZooCalrissianRunner(
            cwl=self.cwl,
            conf=self.conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=CalrissianRunnerExecutionHandler(conf=self.conf),
        )

        exit_value = runner.execute(wall_time=120)

        print(f"exit value: {exit_value}")

        self.assertEqual(exit_value, 3)
