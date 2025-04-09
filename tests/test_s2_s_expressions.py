import base64
import json
import os
import tempfile
import unittest

import yaml

from zoo_calrissian_runner import ZooCalrissianRunner
from zoo_calrissian_runner.handlers import ExecutionHandler
import tests.handler_for_tests as handler

# from dotenv import load_dotenv


# load_dotenv()


class TestSentinel2SExpressions(unittest.TestCase):
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
        conf["lenv"] = {"Identifier": "s-expression"}
        conf["tmpPath"] = "/tmp"

        cls.conf = conf

        with open("tests/app-s-expression.dev.0.0.2.cwl", "r") as stream:
            cwl = yaml.safe_load(stream)

        cls.cwl = cwl

    def test_execution(self):

        inputs = {
            "input_reference": {
                "value": "https://catalog.terradue.com/sentinel2/search?format=atom&uid=S2A_MSIL1C_20220724T100041_N0400_R122_T33TUH_20220724T120137&do=[terradue]"  # noqa: E501
            },  # noqa: E501
            "s_expression": {"value": "(/ (- green red) (+ green red))"},
            "cbn": {"value": "ndvi"},
        }

        outputs = {"Result": {"value": ""}}

        runner = ZooCalrissianRunner(
            cwl=self.cwl,
            conf=self.conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=handler.CalrissianRunnerExecutionHandler(conf=self.conf),
        )

        exit_value = runner.execute()

        print(f"exit value: {exit_value}")

        self.assertEqual(exit_value, 3)

    def test_missing_parameter_execution(self):

        # cbn parameter not provided
        inputs = {
            "input_reference": {
                "value": "https://catalog.terradue.com/sentinel2/search?format=atom&uid=S2A_MSIL1C_20220724T100041_N0400_R122_T33TUH_20220724T120137&do=[terradue]"  # noqa: E501
            },  # noqa: E501
            "s_expression": {"value": "(/ (- nir red) (+ nir red))"},
        }

        outputs = {"Result": {"value": ""}}

        runner = ZooCalrissianRunner(
            cwl=self.cwl,
            conf=self.conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=handler.CalrissianRunnerExecutionHandler(conf=self.conf),
        )

        exit_value = runner.execute()

        print(f"exit value: {exit_value}")

        self.assertEqual(exit_value, 4)
