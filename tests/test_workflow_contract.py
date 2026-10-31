import json
import unittest
from pathlib import Path
from workflow import build_workflow

class InstalledNodeContractTests(unittest.TestCase):
    def test_all_required_inputs_from_comfyui_0430_are_supplied(self):
        contract=json.loads((Path(__file__).parent/'fixtures/comfy-node-inputs.json').read_text(encoding='utf8'))
        graph=build_workflow(['face.png','clothes.png','pose.png'],'test',42)
        for key,node in graph.items():
            with self.subTest(node=key,type=node['class_type']):
                required=set(contract[node['class_type']])
                self.assertEqual(required-set(node['inputs']),set(),'Missing required ComfyUI inputs')

if __name__=='__main__':unittest.main()
