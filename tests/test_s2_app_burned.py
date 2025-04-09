import base64
import json
import os
import tempfile
import unittest

import yaml

from zoo_calrissian_runner import ZooCalrissianRunner

import tests.handler_for_tests as handler
# from dotenv import load_dotenv


# load_dotenv()


class TestSentinel2BurnedArea(unittest.TestCase):
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

            with open("tests/app-burned-area.1.0.cwl", "r") as stream:
                cwl = yaml.safe_load(stream)

            cls.cwl = cwl

    def test_execution(self):

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
            cwl=self.cwl,
            conf=self.conf,
            inputs=inputs,
            outputs=outputs,
            execution_handler=handler.CalrissianRunnerExecutionHandler(conf=self.conf),
        )

        exit_value = runner.execute()

        print(f"exit value: {exit_value}")

        self.assertEqual(exit_value, 3)
