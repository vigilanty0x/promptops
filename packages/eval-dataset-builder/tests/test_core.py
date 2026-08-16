import unittest
from eval_dataset_builder.core import build
class T(unittest.TestCase):
 def test_build(self): self.assertEqual(build([{"input":"a","expected":"b"}])["count"],1)
 def test_dedup(self): self.assertEqual(build([{"input":"a","expected":"b"}]*2)["count"],1)
 def test_stable(self): self.assertEqual(build([{"input":"a","expected":"b"}])["sha256"],build([{"input":"a","expected":"b"}])["sha256"])
 def test_split(self): self.assertIn(build([{"input":"a","expected":"b"}])["items"][0]["split"],{"train","test"})
 def test_schema(self):
  with self.assertRaises(ValueError): build([{"input":"a"}])
if __name__=="__main__": unittest.main()

