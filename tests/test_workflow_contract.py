import json
import unittest
from pathlib import Path
from workflow import add_hairstyle_pass, build_workflow

class InstalledNodeContractTests(unittest.TestCase):
    def test_all_required_inputs_from_comfyui_0430_are_supplied(self):
        contract=json.loads((Path(__file__).parent/'fixtures/comfy-node-inputs.json').read_text(encoding='utf8'))
        for quality in ['fast','quality']:
            graph=build_workflow(['face.png','clothes.png','pose.png','background.png'],'test',42,quality=quality)
            graph=add_hairstyle_pass(graph,'hair.png','hair edit',42,640,896,quality)
            for key,node in graph.items():
                with self.subTest(quality=quality,node=key,type=node['class_type']):
                    required=set(contract[node['class_type']])
                    self.assertEqual(required-set(node['inputs']),set(),'Missing required ComfyUI inputs')

if __name__=='__main__':unittest.main()
