import unittest

from dnbr.service import dnbr
from dotenv import load_dotenv

load_dotenv()


class TestSentinel2DNBRService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class ZooStub(object):
            def __init__(self):
                self.SERVICE_SUCCEEDED = 3
                self.SERVICE_FAILED = 4

            def update_status(self, conf, progress):
                print(f"Status {progress}")

            def _(self, message):
                print(f"invoked _ with {message}")

        try:
            import zoo
        except ImportError:
            print("Not running in zoo instance")

            zoo = ZooStub()

        cls.zoo = zoo

        conf = {}
        conf["lenv"] = {"message": ""}
        conf["lenv"] = {"Identifier": "dnbr"}
        conf["tmpPath"] = "/tmp"

        cls.conf = conf

        inputs = {
            "post_stac_item": {
                "value": "https://earth-search.aws.element84.com/v0/collections/sentinel-s2-l2a-cogs/items/S2B_53HPA_20210723_0_L2A"  # noqa: E501
            },  # noqa: E501
            "pre_stac_item": {
                "value": "https://earth-search.aws.element84.com/v0/collections/sentinel-s2-l2a-cogs/items/S2B_53HPA_20210703_0_L2A"  # noqa: E501
            },  # noqa: E501
            "aoi": {"value": "136.659,-35.96,136.923,-35.791"},
        }

        cls.inputs = inputs

        outputs = {"Result": {"value": ""}}

        cls.outputs = outputs

    def test_execution(self):
        exit_code = dnbr(conf=self.conf, inputs=self.inputs, outputs=self.outputs)

        self.assertEqual(exit_code, self.zoo.SERVICE_SUCCEEDED)
