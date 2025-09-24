import tempfile
import unittest

import yaml
from cwl_utils.parser.cwl_v1_0 import Workflow

from zoo_calrissian_runner import ZooCalrissianRunner


class TestCalrissianContext(unittest.TestCase):
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

            cls.conf = conf

            inputs = {}
            inputs["param_1"] = {"value": "value1"}
            inputs["param_2"] = {"value": "value2"}

            cls.inputs = inputs

            outputs = {}
            outputs["an_output"] = {}

            cls.outputs = outputs

            with open("app-packages/dNBR.cwl", "r") as stream:
                cwl = yaml.safe_load(stream)

            cls.cwl = cwl

    def test_zoo_object(self):
        self.assertEqual(self.zoo.SERVICE_SUCCEEDED, 3)

    def test_object_creation(self):
        inputs = {
            "mock_input": {
                "value": "mock_input_val"  # noqa: E501
            }
        }
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        self.assertIsInstance(runner, ZooCalrissianRunner)

    def test_get_input_invalid_value(self):
        inputs = {}

        inputs["_cwl"] = {"value": "value1"}
        inputs["_workflow_id"] = {"value": "dbnr"}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        with self.assertRaises(KeyError):
            runner.inputs.get_input_value("missing_key")

    def test_get_input_value(self):
        inputs = {}

        inputs["input_1"] = {"value": "value1"}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        self.assertEqual(runner.inputs.get_input_value("input_1"), "value1")

    def test_wrapper(self):
        inputs = {}

        inputs["param_1"] = {"value": "value1"}
        inputs["param_2"] = {"value": "value2"}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        wrapped = runner.wrap()

        self.assertIsInstance(wrapped, dict)

    def test_get_processing_parameters(self):
        inputs = {}

        inputs["param_1"] = {"value": "value1"}
        inputs["param_2"] = {"value": "value2"}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        params = {"param_1": "value1", "param_2": "value2"}

        self.assertEqual(params, runner.get_processing_parameters())

    def test_get_workflow(self):
        inputs = {}

        inputs["param_1"] = {"value": "value1"}
        inputs["param_2"] = {"value": "value2"}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)
        print(type(runner.workflow.get_workflow()))
        self.assertIsInstance(runner.workflow.get_workflow(), Workflow)

    def test_get_wrong_workflow(self):
        conf = {}
        conf["lenv"] = {"message": ""}
        conf["lenv"] = {"Identifier": "not_available"}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=conf, inputs=self.inputs, outputs=outputs)
        with self.assertRaises(ValueError):
            runner.workflow.get_workflow()

    def test_get_workflow_inputs(self):
        inputs = {}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        self.assertEqual(
            set(["pre_stac_item", "post_stac_item", "aoi", "bands"]),
            set(runner.workflow.get_workflow_inputs()),
        )

    def test_get_workflow_inputs_bis(self):
        inputs = {}
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        self.assertEqual(
            set(["pre_stac_item", "post_stac_item", "aoi", "bands"]),
            set(runner.get_workflow_inputs()),
        )

    def test_get_only_mandatory_inputs(self):
        inputs = ()
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)
        self.assertTrue(
            set(runner.get_workflow_inputs(mandatory=True)),
            set(["pre_stac_item", "post_stac_item"]),
        )

    def test_assert_all_parameters_missing(self):
        inputs = {
            "post_stac_item": {
                "value": "https://earth-search.aws.element84.com/v0/collections/sentinel-s2-l2a-cogs/items/S2B_53HPA_20210723_0_L2A"  # noqa: E501
            },
            "aoi": {"value": "136.659,-35.96,136.923,-35.791"},
        }
        outputs = {"Result": {"value": ""}}
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)
        print(list(runner.get_processing_parameters().keys()))
        print(runner.get_workflow_inputs(mandatory=True))
        self.assertFalse(runner.assert_parameters())

    def test_assert_all_parameters(self):
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
        runner = ZooCalrissianRunner(cwl=self.cwl, conf=self.conf, inputs=inputs, outputs=outputs)

        self.assertTrue(runner.assert_parameters())
